#!/usr/bin/env python3
#
# Eden notifications: e-mail alerts through the user's own SMTP server. Standard library only.
# Imported by eden_remote and eden_local (event() never raises and never blocks the caller) and used as a
# small CLI by start.sh:
#     eden_notify.py event <event_id> [detail]     send one event, honouring the settings
#     eden_notify.py test                          send the test message, exit 1 on failure
#
# Settings live in config/eden.json under "notifications" (nothing secret); the SMTP password is the file
# secrets/smtp.password and is never written anywhere else. Environment (set by start.sh): EDEN_CONFIG,
# EDEN_SECRETS, EDEN_RUN.
#
# What the mails never contain: passwords, TOTP codes, session tokens. The subject comes only from the
# catalog below; text that originates outside Eden (an address, a browser name) appears only in the body,
# stripped of control characters, so it cannot inject headers.

import email.utils
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from email.message import EmailMessage

SMTP_TIMEOUT = 10          # seconds, for connect and for every SMTP exchange
MAX_PER_HOUR = 20          # hard cap on mails per process per hour: a flood of events must not flood the inbox
DEFAULT_COOLDOWN_MINUTES = 10
SECURITY_MODES = ("ssl", "starttls", "none")

# The catalog: what can be notified. "grouped" events are rate-limited per source (one mail per
# cooldown, with a count of the ones held back); the others are always sent (subject to MAX_PER_HOUR).
# "default" is the on/off state when the user has not touched the switch.
CATALOG = [
    {"id": "login_failed", "default": True, "grouped": True, "source": "Eden remote",
     "label": {"en": "Failed login attempt", "it": "Tentativo di accesso fallito"},
     "description": {"en": "Wrong password or TOTP code on the login page. To keep the inbox from filling up, one message per address "
                           "arrives every chosen pause, with the number of attempts.",
                     "it": "Password o codice TOTP errati nella pagina di login. Per non riempire la casella arriva un solo messaggio per "
                           "indirizzo ogni pausa scelta, con il numero dei tentativi."}},
    {"id": "login_lockout", "default": True, "grouped": False, "source": "Eden remote",
     "label": {"en": "Login locked after too many attempts", "it": "Accesso bloccato per troppi tentativi"},
     "description": {"en": "An address used up its allowed attempts and was locked out.",
                     "it": "Un indirizzo ha esaurito i tentativi consentiti ed è stato bloccato."}},
    {"id": "login_success", "default": True, "grouped": False, "source": "Eden remote",
     "label": {"en": "Remote login succeeded", "it": "Accesso remoto riuscito"},
     "description": {"en": "Someone entered the correct password and TOTP and got in.",
                     "it": "Qualcuno ha inserito password e TOTP corretti ed è entrato."}},
    {"id": "enroll_opened", "default": True, "grouped": False, "source": "Eden local",
     "label": {"en": "Reset window opened", "it": "Finestra di reimpostazione aperta"},
     "description": {"en": "The window to change password and TOTP was opened from Settings: the current ones were deleted.",
                     "it": "Da Impostazioni è stata aperta la finestra per cambiare password e TOTP: quelli attuali sono stati cancellati."}},
    {"id": "enroll_completed", "default": True, "grouped": False, "source": "Eden remote",
     "label": {"en": "Password and TOTP reset", "it": "Password e TOTP reimpostati"},
     "description": {"en": "Someone completed the password and TOTP setup from the Eden remote page.",
                     "it": "Qualcuno ha completato la configurazione di password e TOTP dalla pagina di Eden remote."}},
    {"id": "access_widened", "default": True, "grouped": False, "source": "Eden local",
     "label": {"en": "Access widened", "it": "Accesso ampliato"},
     "description": {"en": "A service was turned on, a device was added or enabled, or a permission was granted.",
                     "it": "Un servizio è stato acceso, un dispositivo è stato aggiunto o abilitato, o un permesso è stato concesso."}},
    {"id": "eden_started", "default": False, "grouped": False, "source": "start.sh",
     "label": {"en": "Eden started", "it": "Eden avviato"},
     "description": {"en": "Eden was started, also after a restart from the Settings page.",
                     "it": "Eden è stato avviato, anche dopo un riavvio dalla pagina Impostazioni."}},
]
CATALOG_BY_ID = {e["id"]: e for e in CATALOG}

# Texts of the mails and of the test result, in the language set in Settings (ui.language, "en" default).
TEXTS = {
    "event": {"en": "Event: {v}", "it": "Evento: {v}"},
    "when": {"en": "When: {v}", "it": "Quando: {v}"},
    "from": {"en": "From: {v}", "it": "Da: {v}"},
    "details": {"en": "Details: {v}", "it": "Dettagli: {v}"},
    "held": {"en": "Other identical events in the last {minutes} minutes, not notified one by one: {n}",
             "it": "Altri eventi uguali nelle ultime {minutes} minuti, non notificati uno per uno: {n}"},
    "footer": {"en": "Eden on {host}. To change these notifications: Eden > Notifications.",
               "it": "Eden su {host}. Per cambiare queste notifiche: Eden > Notifiche."},
    "testSubject": {"en": "Test email", "it": "Email di prova"},
    "testLine1": {"en": "This is a test email sent by Eden.", "it": "Questa è un'email di prova inviata da Eden."},
    "testLine2": {"en": "If you can read it, notifications can reach you.", "it": "Se la leggi, le notifiche possono arrivare."},
    "testSent": {"en": "Test email sent.", "it": "Email di prova inviata."},
    "testMissing": {"en": "Server, sender or recipient are missing: save the mail server details first.",
                    "it": "Mancano server, mittente o destinatario: salva prima i dati del server di posta."},
}

DEFAULT_SMTP = {"host": "", "port": 587, "security": "starttls", "verify_tls": True,
                "username": "", "sender": "", "recipient": ""}

_lock = threading.Lock()
_last_sent = {}      # (event id, source) -> monotonic time of the last mail
_held_back = {}      # (event id, source) -> events skipped since that mail
_sent_times = deque()  # monotonic times of the mails sent in the last hour


def language():
    """ui.language from the config ("en" or "it"); English when it cannot be read."""
    try:
        with open(os.environ["EDEN_CONFIG"]) as f:
            ui = json.load(f).get("ui")
        lang = ui.get("language") if isinstance(ui, dict) else None
    except (KeyError, OSError, ValueError):
        lang = None
    return lang if lang in ("en", "it") else "en"


def _t(key, lang, **fields):
    return TEXTS[key][lang].format(**fields)


def label(event_id, lang=None):
    """Name of an event in the given (default: current) language."""
    return CATALOG_BY_ID[event_id]["label"][lang or language()]


def description(event_id, lang=None):
    return CATALOG_BY_ID[event_id]["description"][lang or language()]


def _log(msg):
    print(f"eden_notify: {msg}", file=sys.stderr, flush=True)


def _clean(text, limit=200):
    """One line of printable text: control characters become spaces, length is capped."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()[:limit]


# ---- settings -------------------------------------------------------------------------------------------------
def _raw_config():
    try:
        with open(os.environ["EDEN_CONFIG"]) as f:
            cfg = json.load(f)
    except (KeyError, OSError, ValueError):
        return {}
    raw = cfg.get("notifications")
    return raw if isinstance(raw, dict) else {}


def settings(raw=None):
    """The notification settings with every default filled in."""
    raw = _raw_config() if raw is None else raw
    smtp = {**DEFAULT_SMTP, **(raw.get("smtp") if isinstance(raw.get("smtp"), dict) else {})}
    if smtp["security"] not in SECURITY_MODES:
        smtp["security"] = DEFAULT_SMTP["security"]
    try:
        cooldown = max(1, int(raw.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES)))
    except (TypeError, ValueError):
        cooldown = DEFAULT_COOLDOWN_MINUTES
    stored = raw.get("events") if isinstance(raw.get("events"), dict) else {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "cooldown_minutes": cooldown,
        "smtp": smtp,
        "events": {e["id"]: bool(stored.get(e["id"], e["default"])) for e in CATALOG},
    }


def configured(smtp):
    return bool(smtp["host"] and smtp["sender"] and smtp["recipient"])


def password_file():
    return os.path.join(os.environ.get("EDEN_SECRETS", ""), "smtp.password")


def password_set():
    return os.path.isfile(password_file())


def _read_password():
    try:
        with open(password_file(), encoding="utf-8") as f:
            return f.read().rstrip("\r\n")
    except OSError:
        return ""


def read_status():
    """Outcome of the last send attempt ({"at", "ok", "event", "error"}) or None."""
    try:
        with open(os.path.join(os.environ["EDEN_RUN"], "notify.status.json")) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (KeyError, OSError, ValueError):
        return None


def _write_status(ok, event_id, error=""):
    try:
        run = os.environ["EDEN_RUN"]
        fd, tmp = tempfile.mkstemp(dir=run, prefix=".notify.status.")
        with os.fdopen(fd, "w") as f:
            json.dump({"at": time.time(), "ok": ok, "event": event_id, "error": error}, f)
        os.replace(tmp, os.path.join(run, "notify.status.json"))
    except (KeyError, OSError):
        pass


# ---- sending --------------------------------------------------------------------------------------------------
def _deliver(msg, smtp, password):
    """Send one message. Raises on any failure (the caller turns it into text)."""
    ctx = ssl.create_default_context()
    if not smtp["verify_tls"]:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    host, port, local = smtp["host"], int(smtp["port"]), socket.gethostname()   # local name given: no slow reverse lookup
    if smtp["security"] == "ssl":
        conn = smtplib.SMTP_SSL(host, port, local_hostname=local, timeout=SMTP_TIMEOUT, context=ctx)
    else:
        conn = smtplib.SMTP(host, port, local_hostname=local, timeout=SMTP_TIMEOUT)
    with conn:
        conn.ehlo()
        if smtp["security"] == "starttls":
            conn.starttls(context=ctx)
            conn.ehlo()
        if smtp["username"]:
            conn.login(smtp["username"], password)
        conn.send_message(msg)


def _message(subject, lines, smtp, lang):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp["sender"]
    msg["To"] = smtp["recipient"]
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=smtp["sender"].rsplit("@", 1)[-1])
    msg.set_content("\n".join(lines) + "\n\n--\n" + _t("footer", lang, host=socket.gethostname()) + "\n")
    return msg


def _error_text(exc):
    return _clean(f"{type(exc).__name__}: {exc}", 300)


def _send_event(spec, source, detail, held):
    cfg, lang = settings(), language()
    name = spec["label"][lang]
    lines = [_t("event", lang, v=name), _t("when", lang, v=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"))]
    if source:
        lines.append(_t("from", lang, v=_clean(source)))
    if detail:
        lines.append(_t("details", lang, v=_clean(detail)))
    if held:
        lines.append(_t("held", lang, minutes=cfg["cooldown_minutes"], n=held))
    try:
        _deliver(_message(f"[Eden] {name}", lines, cfg["smtp"], lang), cfg["smtp"], _read_password())
        _write_status(True, spec["id"])
    except Exception as exc:   # noqa: BLE001 - any failure must be reported, never raised into the caller
        _log(f"{spec['id']}: send failed: {_error_text(exc)}")
        _write_status(False, spec["id"], _error_text(exc))


def event(event_id, source="", detail=""):
    """Report an event. Returns the sending thread (or None when nothing is sent). Never raises, never blocks."""
    try:
        spec = CATALOG_BY_ID.get(event_id)
        if spec is None:
            _log(f"unknown event {event_id!r}")
            return None
        cfg = settings()
        if not (cfg["enabled"] and cfg["events"][event_id] and configured(cfg["smtp"])):
            return None
        key, held = (event_id, source), 0
        with _lock:
            now = time.monotonic()
            if spec["grouped"]:
                last = _last_sent.get(key)
                if last is not None and now - last < cfg["cooldown_minutes"] * 60:
                    _held_back[key] = _held_back.get(key, 0) + 1
                    return None
            while _sent_times and now - _sent_times[0] > 3600:
                _sent_times.popleft()
            if len(_sent_times) >= MAX_PER_HOUR:
                _log(f"{event_id}: hourly limit of {MAX_PER_HOUR} mails reached, event dropped")
                return None
            _sent_times.append(now)
            _last_sent[key] = now
            held = _held_back.pop(key, 0)
        thread = threading.Thread(target=_send_event, args=(spec, source, detail, held), daemon=True)
        thread.start()
        return thread
    except Exception as exc:   # noqa: BLE001
        _log(f"{event_id}: {_error_text(exc)}")
        return None


def send_test():
    """Send the test message with the saved settings, whatever the on/off switches say. Returns (ok, text)."""
    cfg, lang = settings(), language()
    if not configured(cfg["smtp"]):
        return False, _t("testMissing", lang)
    lines = [_t("testLine1", lang), _t("when", lang, v=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")), _t("testLine2", lang)]
    try:
        _deliver(_message("[Eden] " + _t("testSubject", lang), lines, cfg["smtp"], lang), cfg["smtp"], _read_password())
    except Exception as exc:   # noqa: BLE001
        _write_status(False, "test", _error_text(exc))
        return False, _error_text(exc)
    _write_status(True, "test")
    return True, _t("testSent", lang)


def main(argv):
    if len(argv) >= 3 and argv[1] == "event":
        thread = event(argv[2], detail=" ".join(argv[3:]))
        if thread:
            thread.join(SMTP_TIMEOUT * 3)
        return 0
    if len(argv) == 2 and argv[1] == "test":
        ok, text = send_test()
        print(text)
        return 0 if ok else 1
    print("usage: eden_notify.py event <event_id> [detail] | test", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
