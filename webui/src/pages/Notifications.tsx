// Notifications page: the mail server Eden sends alerts through, and one switch per event. The SMTP password is
// write-only: the backend never sends it back, the form shows whether one is stored.
import { useCallback, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Card } from "@workspace/pds/components/ui/card";
import { Field } from "@workspace/pds/components/ui/field";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemSeparator, ItemTitle } from "@workspace/pds/components/ui/item";
import { toast } from "@workspace/pds/hooks/use-toast";
import { apiGet, apiPost } from "../lib/api";
import Feedback from "../components/Feedback";
import OnOff from "../components/OnOff";
import PageStack from "../components/PageStack";
import PageLoading from "../components/PageLoading";
import ToggleRow from "../components/ToggleRow";
import { useFieldSize } from "../lib/useFieldSize";
import { useT } from "../lib/i18n";

type Security = "ssl" | "starttls" | "none";
type Smtp = {
  host: string;
  port: number;
  security: Security;
  verify_tls: boolean;
  username: string;
  sender: string;
  recipient: string;
  password_set: boolean;
};
type NotifEvent = { id: string; label: string; description: string; source: string; enabled: boolean };
type Notif = {
  enabled: boolean;
  cooldown_minutes: number;
  configured: boolean;
  smtp: Smtp;
  events: NotifEvent[];
  status: { at: number; ok: boolean; event: string; error: string } | null;
};

const HOST_RE = /^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$/;
const EMAIL_RE = /^[^@\s<>"',;()[\]\\]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$/;
const COOLDOWNS = [1, 5, 10, 30, 60];
const withCurrent = (list: number[], cur: number) => (list.includes(cur) ? list : [...list, cur].sort((a, b) => a - b));
const DEFAULT_PORT: Record<Security, string> = { ssl: "465", starttls: "587", none: "25" };
const errorStyle = { color: "var(--color-destructive)" } as const;
const wide = { display: "block", overflow: "visible", WebkitLineClamp: "none" } as const;

export default function Notifications() {
  const { t, locale } = useT();
  const fieldSize = useFieldSize();
  const [data, setData] = useState<Notif | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState(false);

  // The form. It is filled from the server once, and again after each save; polling would overwrite what is being typed.
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [security, setSecurity] = useState<Security>("starttls");
  const [verifyTls, setVerifyTls] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState(""); // empty = keep the stored one
  const [sender, setSender] = useState("");
  const [recipient, setRecipient] = useState("");

  const fill = (s: Smtp) => {
    setHost(s.host);
    setPort(String(s.port));
    setSecurity(s.security);
    setVerifyTls(s.verify_tls);
    setUsername(s.username);
    setPassword("");
    setSender(s.sender);
    setRecipient(s.recipient);
  };
  const filled = useRef(false);
  const load = useCallback(() => {
    apiGet<Notif>("/notifications")
      .then((r) => {
        setData(r);
        if (!filled.current) {
          filled.current = true;
          fill(r.smtp);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  // Runs one change; the backend answers with the full new state. Resolves to it, or null on failure.
  const run = async (call: () => Promise<Notif>, doneMsg?: string): Promise<Notif | null> => {
    setBusy(true);
    setError(null);
    try {
      const r = await call();
      setData(r);
      if (doneMsg) toast({ description: doneMsg });
      return r;
    } catch (e) {
      setError(String(e));
      load(); // resync, and refresh the "last send" line after a failed test
      return null;
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <PageLoading title={t("notif.title")} error={error} />;

  const stored = data.smtp;
  const portNum = Number(port);
  const errors = {
    host: HOST_RE.test(host.trim()) ? null : t("notif.hostError"),
    port: Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535 ? null : t("notif.portError"),
    sender: EMAIL_RE.test(sender.trim()) ? null : t("notif.emailError"),
    recipient: EMAIL_RE.test(recipient.trim()) ? null : t("notif.emailError"),
  };
  const invalid = Object.values(errors).some(Boolean);
  const dirty =
    host.trim() !== stored.host || portNum !== stored.port || security !== stored.security || verifyTls !== stored.verify_tls ||
    username.trim() !== stored.username || sender.trim() !== stored.sender || recipient.trim() !== stored.recipient || password !== "";
  const shown = (key: keyof typeof errors) => (tried && errors[key] ? "error" : "default");

  const save = async () => {
    setTried(true);
    if (invalid) return;
    const body = { host: host.trim(), port: portNum, security, verify_tls: verifyTls, username: username.trim(), sender: sender.trim(),
                   recipient: recipient.trim(), password: password === "" ? null : password };
    const r = await run(() => apiPost<Notif>("/notifications/smtp", body), t("notif.saved"));
    if (r) {
      fill(r.smtp);
      setTried(false);
    }
  };
  const removePassword = () => run(() => apiPost<Notif>("/notifications/smtp", {
    host: stored.host, port: stored.port, security: stored.security, verify_tls: stored.verify_tls, username: stored.username,
    sender: stored.sender, recipient: stored.recipient, password: "" }), t("notif.passwordRemoved"));
  const sendTest = () => run(() => apiPost<Notif & { message: string }>("/notifications/test"), t("notif.testSent"));

  const changeSecurity = (v: Security) => {
    setSecurity(v);
    if (Object.values(DEFAULT_PORT).includes(port)) setPort(DEFAULT_PORT[v]); // a standard port follows the mode; a custom one stays
  };
  const label = (id: string) => (id === "test" ? t("notif.testName") : data.events.find((e) => e.id === id)?.label ?? id);

  return (
    <PageStack>
      <h1 className="text-xl font-semibold">{t("notif.title")}</h1>
      <p className="text-sm text-muted-foreground">
        {t("notif.description")}
      </p>

      <h2 className="pt-4 text-sm font-semibold">{t("notif.serverTitle")}</h2>
      {/* The fields sit directly on the page, not in a Card: PDS colours a Field for the page canvas (or a Sheet), so inside a Card
          the fill style disappears (same colour as the card) and the outline style gets a box that does not match it. */}
      <Stack gap="s" className="py-1">
          <div>
            <Field size={fieldSize} label={t("notif.hostLabel")} value={host} autoComplete="off" state={shown("host")} onChange={(e) => setHost(e.target.value)} />
            <p className="text-xs" style={tried && errors.host ? errorStyle : { opacity: 0.7 }}>
              {tried && errors.host ? errors.host : t("notif.hostHelp")}
            </p>
          </div>
          <div>
            <Field size={fieldSize} label={t("notif.portLabel")} type="number" inputMode="numeric" min={1} max={65535} value={port} state={shown("port")} onChange={(e) => setPort(e.target.value)} />
            <p className="text-xs" style={tried && errors.port ? errorStyle : { opacity: 0.7 }}>
              {tried && errors.port ? errors.port : t("notif.portHelp")}
            </p>
          </div>
          <div>
            <Field size={fieldSize} label={t("notif.userLabel")} value={username} autoComplete="off" onChange={(e) => setUsername(e.target.value)} />
            <p className="text-xs" style={{ opacity: 0.7 }}>{t("notif.userHelp")}</p>
          </div>
          <div>
            <Field size={fieldSize}
              label={stored.password_set ? t("notif.passwordNew") : t("notif.passwordLabel")}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="text-xs" style={{ opacity: 0.7 }}>
              {stored.password_set
                ? t("notif.passwordHelpSet")
                : t("notif.passwordHelpUnset")}
            </p>
            {stored.password_set && (
              <Button variant="link" size="small" disabled={busy} onClick={removePassword}>
                {t("notif.passwordRemove")}
              </Button>
            )}
          </div>
          <div>
            <Field size={fieldSize} label={t("notif.senderLabel")} type="email" autoComplete="off" value={sender} state={shown("sender")} onChange={(e) => setSender(e.target.value)} />
            <p className="text-xs" style={tried && errors.sender ? errorStyle : { opacity: 0.7 }}>
              {tried && errors.sender ? errors.sender : t("notif.senderHelp")}
            </p>
          </div>
          <div>
            <Field size={fieldSize} label={t("notif.recipientLabel")} type="email" autoComplete="off" value={recipient} state={shown("recipient")} onChange={(e) => setRecipient(e.target.value)} />
            <p className="text-xs" style={tried && errors.recipient ? errorStyle : { opacity: 0.7 }}>
              {tried && errors.recipient ? errors.recipient : t("notif.recipientHelp")}
            </p>
          </div>
      </Stack>
      <Card>
        <ItemGroup>
          <ToggleRow
            label={t("notif.securityTitle")}
            description={t("notif.securityDescription")}
            value={security}
            onChange={(v) => changeSecurity(v as Security)}
            options={[
              { value: "ssl", label: "SSL" },
              { value: "starttls", label: "STARTTLS" },
              { value: "none", label: t("notif.securityNone") },
            ]}
          />
          {security !== "none" && (
            <>
              <ItemSeparator />
              <Item size="sm">
                <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
                  <ItemTitle>{t("notif.verifyTitle")}</ItemTitle>
                  <ItemDescription style={wide}>
                    {t("notif.verifyDescription")}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <OnOff label={t("notif.verifyTitle")} value={verifyTls} onChange={setVerifyTls} />
                </ItemActions>
              </Item>
            </>
          )}
        </ItemGroup>
      </Card>
      {security === "none" && (
        <Alert>
          <AlertDescription>
            {t("notif.noneWarning")}
          </AlertDescription>
        </Alert>
      )}

      <Row gap="ss">
        <Button variant="default" size="small" disabled={busy || !dirty} onClick={save}>
          {t("notif.save")}
        </Button>
        <Button variant="default" size="small" disabled={busy || dirty || !data.configured} onClick={sendTest}>
          <Send /> {t("notif.sendTest")}
        </Button>
      </Row>
      {dirty && data.configured && <p className="text-xs text-muted-foreground">{t("notif.saveFirst")}</p>}
      {data.status && (
        <p className="text-xs text-muted-foreground">
          {t("notif.lastSend", { what: label(data.status.event), when: new Date(data.status.at * 1000).toLocaleString(locale) })}{" "}
          {data.status.ok ? t("notif.lastOk") : t("notif.lastFailed", { error: data.status.error })}
        </p>
      )}
      <Feedback busy={busy} error={error} />

      <h2 className="pt-4 text-sm font-semibold">{t("notif.eventsTitle")}</h2>
      {!data.configured && (
        <Alert>
          <AlertDescription>{t("notif.notConfigured")}</AlertDescription>
        </Alert>
      )}
      <Card>
        <ItemGroup>
          <Item size="sm">
            <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
              <ItemTitle>{t("notif.enabledTitle")}</ItemTitle>
              <ItemDescription style={wide}>{t("notif.enabledDescription")}</ItemDescription>
            </ItemContent>
            <ItemActions>
              <OnOff
                label={t("notif.enabledTitle")}
                text={data.enabled ? t("notif.enabledOn") : t("notif.enabledOff")}
                value={data.enabled}
                disabled={busy}
                onChange={(v) => run(() => apiPost<Notif>("/notifications/settings", { enabled: v, cooldown_minutes: data.cooldown_minutes }))}
              />
            </ItemActions>
          </Item>
          <ItemSeparator />
          <ToggleRow
            label={t("notif.cooldownTitle")}
            description={t("notif.cooldownDescription")}
            value={String(data.cooldown_minutes)}
            disabled={busy}
            onChange={(v) => run(() => apiPost<Notif>("/notifications/settings", { enabled: data.enabled, cooldown_minutes: Number(v) }))}
            options={withCurrent(COOLDOWNS, data.cooldown_minutes).map((n) => ({ value: String(n), label: String(n) }))}
          />
          {data.events.map((e) => (
            <div key={e.id} style={{ opacity: data.enabled ? 1 : 0.6 }}>
              <ItemSeparator />
              <Item size="sm">
                <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
                  <ItemTitle>{e.label}</ItemTitle>
                  <ItemDescription style={wide}>{e.description}</ItemDescription>
                  <div className="text-xs text-muted-foreground">{t("notif.source", { source: e.source })}</div>
                </ItemContent>
                <ItemActions>
                  <OnOff
                    label={e.label}
                    value={e.enabled}
                    disabled={busy}
                    onChange={(v) => run(() => apiPost<Notif>(`/notifications/events/${e.id}`, { enabled: v }))}
                  />
                </ItemActions>
              </Item>
            </div>
          ))}
        </ItemGroup>
      </Card>
      <p className="text-xs text-muted-foreground">
        {t("notif.footer")}
      </p>
    </PageStack>
  );
}
