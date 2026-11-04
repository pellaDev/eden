# Texts of the API's error messages, in the two languages of the UI ("ui.language" in eden.json: "en" default, "it").
# A message is looked up by key; an unknown key or language falls back to English, then to the key itself, so a missing
# translation can never break a request. Placeholders use str.format fields.
LANGUAGES = ("en", "it")
DEFAULT_LANGUAGE = "en"

MESSAGES = {
    "terminal_open_failed": {
        "en": "could not open a terminal. Open one yourself and run: sudoedit {file}",
        "it": "non sono riuscito ad aprire un terminale. Aprine uno tu ed esegui: sudoedit {file}",
    },
    "busy": {
        "en": "another operation is in progress, try again shortly",
        "it": "un'altra operazione è in corso, riprova tra poco",
    },
    "services_changed": {
        "en": "the list of services has changed: reload the page and try again",
        "it": "l'elenco dei servizi è cambiato: ricarica la pagina e riprova",
    },
    "service_name_invalid": {
        "en": "service name: 1-32 characters, lowercase letters, digits, - and _ (must start with a letter or a digit)",
        "it": "nome servizio: 1-32 caratteri, lettere minuscole, numeri, - e _ (deve iniziare con una lettera o un numero)",
    },
    "device_name_invalid": {
        "en": "device name: 1-32 characters, lowercase letters, digits, - and _ (must start with a letter or a digit)",
        "it": "nome dispositivo: 1-32 caratteri, lettere minuscole, numeri, - e _ (deve iniziare con una lettera o un numero)",
    },
    "port_range": {"en": "port: 1-65535", "it": "porta: 1-65535"},
    "note_too_long": {
        "en": "description: at most {max} characters",
        "it": "descrizione: massimo {max} caratteri",
    },
    "avatar_invalid": {
        "en": "invalid picture: a small PNG, JPG, WebP or GIF image is required",
        "it": "avatar non valido: serve una piccola immagine PNG, JPG, WebP o GIF",
    },
    "forward_min_port": {
        "en": "forwarding needs a port of {min} or above",
        "it": "l'inoltro richiede una porta da {min} in su",
    },
    "forward_min_port_hint": {
        "en": "forwarding needs a port of {min} or above: turn forwarding off or change the port",
        "it": "l'inoltro richiede una porta da {min} in su: spegni l'inoltro o cambia porta",
    },
    "remote_service_exists": {
        "en": "a remote service named {name} already exists",
        "it": "esiste già un servizio remoto chiamato {name}",
    },
    "remote_device_required": {
        "en": "choose the device that offers the service (a Meshnet peer)",
        "it": "scegli il dispositivo che offre il servizio (un peer Meshnet)",
    },
    "service_exists": {
        "en": "a service named {name} already exists",
        "it": "esiste già un servizio chiamato {name}",
    },
    "port_is_remote": {
        "en": "port {port} is the Eden remote port",
        "it": "la porta {port} è quella di Eden remote",
    },
    "port_in_use": {
        "en": "port {port} is already used by the service {service}",
        "it": "la porta {port} è già usata dal servizio {service}",
    },
    "port_not_allowed": {
        "en": "port {port} is not among those allowed by the root helper ({file}): the service cannot be turned on",
        "it": "la porta {port} non è tra quelle consentite dall'helper di root ({file}): il servizio non si può accendere",
    },
    "untrusted_remote_port": {
        "en": "an untrusted device cannot have port {port}: it is Eden's remote login port",
        "it": "un dispositivo untrusted non può avere la porta {port}: è quella del login remoto di Eden",
    },
    "restart_unavailable": {
        "en": "Eden was not started in foreground mode (start.sh without arguments): it cannot be restarted from here",
        "it": "Eden non è stato avviato in modalità foreground (start.sh senza argomenti): da qui non si può riavviare",
    },
    "session_timeout_range": {
        "en": "session timeout: 0-1440 minutes (0 = never)",
        "it": "timeout sessione: 0-1440 minuti (0 = mai)",
    },
    "lockout_attempts_range": {
        "en": "attempts before lockout: 1-20",
        "it": "tentativi prima del blocco: 1-20",
    },
    "lockout_minutes_range": {
        "en": "lockout duration: 1-120 minutes",
        "it": "durata del blocco: 1-120 minuti",
    },
    "remote_not_running": {
        "en": "eden_remote is not running: turn the VPN on first",
        "it": "eden_remote non è attivo: accendi prima la VPN",
    },
    "remote_restart_failed": {
        "en": "eden_remote did not restart (window open, remote access stopped): {detail}",
        "it": "eden_remote non si è riavviato (finestra aperta, accesso remoto fermo): {detail}",
    },
    "theme_invalid": {"en": "theme: light or dark", "it": "tema: light o dark"},
    "field_style_invalid": {"en": "field style: fill or outline", "it": "stile campi: fill o outline"},
    "language_invalid": {"en": "language: en or it", "it": "lingua: en o it"},
    "smtp_host_invalid": {
        "en": "server: invalid name or address (letters, digits, dots and hyphens)",
        "it": "server: nome o indirizzo non valido (lettere, numeri, punti e trattini)",
    },
    "smtp_security_invalid": {
        "en": "security: ssl, starttls or none",
        "it": "sicurezza: ssl, starttls o none",
    },
    "smtp_username_invalid": {
        "en": "user: at most 256 characters, no control characters",
        "it": "utente: massimo 256 caratteri, senza caratteri di controllo",
    },
    "email_invalid": {"en": "{label}: invalid e-mail address", "it": "{label}: indirizzo email non valido"},
    "label_sender": {"en": "sender", "it": "mittente"},
    "label_recipient": {"en": "recipient", "it": "destinatario"},
    "smtp_password_invalid": {
        "en": "password: at most 256 characters, no control characters",
        "it": "password: massimo 256 caratteri, senza caratteri di controllo",
    },
    "cooldown_range": {
        "en": "pause between identical e-mails: 1-1440 minutes",
        "it": "pausa tra email uguali: 1-1440 minuti",
    },
    "event_unknown": {"en": "unknown event: {id}", "it": "evento sconosciuto: {id}"},
    "vpn_off_add_device": {
        "en": "VPN is off or the peers cannot be read: turn the VPN on to add a device",
        "it": "VPN spenta o peer non leggibili: accendi la VPN per aggiungere un dispositivo",
    },
    "peer_not_found": {
        "en": "peer not found among the current Meshnet peers",
        "it": "peer non trovato tra i peer Meshnet attuali",
    },
    "address_invalid": {
        "en": "not a Meshnet address: use the device's 100.x.x.x address shown in the Nord app",
        "it": "non è un indirizzo Meshnet: usa l'indirizzo 100.x.x.x del dispositivo mostrato nell'app Nord",
    },
    "address_exists": {"en": "a device with this address is already configured", "it": "esiste già un dispositivo con questo indirizzo"},
    "device_exists_cfg": {"en": "device already configured", "it": "dispositivo già configurato"},
    "vpn_off_check_external": {
        "en": "VPN is off or the peers cannot be read: turn the VPN on, it is needed to check that the device is not external",
        "it": "VPN spenta o peer non leggibili: accendi la VPN, serve per verificare che il dispositivo non sia esterno",
    },
    "peer_missing_check_external": {
        "en": "the device is not among the current Meshnet peers: cannot check that it is not external",
        "it": "il dispositivo non è tra i peer Meshnet attuali: non posso verificare che non sia esterno",
    },
    "device_is_external": {
        "en": "this is an external device (another Nord account): it always stays untrusted",
        "it": "è un dispositivo esterno (altro account Nord): resta sempre untrusted",
    },
    "device_name_taken": {
        "en": "a device named {name} already exists",
        "it": "esiste già un dispositivo chiamato {name}",
    },
    "monitor_range_invalid": {
        "en": "{label}: {lo}-{hi}",
        "it": "{label}: {lo}-{hi}",
    },
    "label_refresh": {"en": "refresh (seconds)", "it": "aggiornamento (secondi)"},
    "label_presence": {"en": "device check (seconds)", "it": "controllo dispositivi (secondi)"},
    "label_retention": {"en": "retention (days)", "it": "conservazione (giorni)"},
    "history_range_unknown": {"en": "unknown range: {range}", "it": "intervallo sconosciuto: {range}"},
    "host_name_invalid": {
        "en": "name: 1-32 characters, letters, digits, space, dot, hyphen",
        "it": "nome: 1-32 caratteri, lettere, numeri, spazio, punto, trattino",
    },
    "journalctl_unavailable": {"en": "journalctl not available: {error}", "it": "journalctl non disponibile: {error}"},
    "journalctl_failed": {"en": "journalctl failed: {detail}", "it": "journalctl fallito: {detail}"},
    "lifecycle_timeout": {
        "en": "start.sh {action}: timeout after {seconds}s",
        "it": "start.sh {action}: timeout dopo {seconds}s",
    },
    "peers_unavailable": {"en": "the Meshnet device list is not available right now", "it": "l'elenco dei dispositivi Meshnet non è disponibile in questo momento"},
    "ev_service_on": {"en": "service {name} turned on", "it": "servizio {name} acceso"},
    "ev_device_service": {"en": "device {device} can use service {service}", "it": "il dispositivo {device} può usare il servizio {service}"},
    "ev_enroll_opened": {
        "en": "{minutes}-minute window: current password and TOTP deleted",
        "it": "finestra di {minutes} minuti: password e TOTP attuali cancellati",
    },
    "ev_untrusted_cleared": {"en": "device {device} is no longer untrusted", "it": "il dispositivo {device} non è più untrusted"},
    "ev_device_enabled": {"en": "device {device} enabled", "it": "dispositivo {device} abilitato"},
    "ev_login_failed": {"en": "attempt no. {count}; {browser}", "it": "tentativo n. {count}; {browser}"},
    "ev_login_lockout": {
        "en": "{count} failed attempts; locked for {minutes} minutes",
        "it": "{count} tentativi falliti; bloccato per {minutes} minuti",
    },
}


def message(lang, key, **fields):
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
    try:
        return text.format(**fields)
    except (KeyError, IndexError, ValueError):
        return text
