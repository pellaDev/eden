import { useCallback, useEffect, useState } from "react";
import { RotateCw } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Card } from "@workspace/pds/components/ui/card";
import { Field } from "@workspace/pds/components/ui/field";
import { Progress } from "@workspace/pds/components/ui/progress";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemSeparator, ItemTitle } from "@workspace/pds/components/ui/item";
import { Tag } from "@workspace/pds/components/ui/tag";
import { usePdsConfig, setPdsConfig } from "@workspace/pds/config";
import { useTheme } from "../lib/theme";
import { useHost } from "../lib/host";
import { useT } from "../lib/i18n";
import { useWindows } from "../lib/platform";
import { useFieldSize } from "../lib/useFieldSize";
import { toast } from "@workspace/pds/hooks/use-toast";
import { apiGet, apiPost } from "../lib/api";
import { usePoll } from "../lib/usePoll";
import Confirm from "../components/Confirm";
import Feedback from "../components/Feedback";
import PageStack from "../components/PageStack";
import LiveSettings from "../components/LiveSettings";
import RestartOverlay from "../components/RestartOverlay";
import ToggleRow from "../components/ToggleRow";

type Enroll = {
  enrolled: boolean;
  window_remaining: number;
  window_minutes: number;
  remote_running: boolean;
  url: string | null;
};
type RemoteSettings = {
  session_timeout_minutes: number;
  lockout_attempts: number;
  lockout_minutes: number;
  remote_port: number | null;
  restart_available?: boolean; // true only when Eden runs from the foreground start.sh (foreground mode)
  enroll: Enroll;
};

// Preset choices; a value already in the config but not listed here is shown as an extra option.
const TIMEOUTS = [5, 15, 30, 60, 0];
const ATTEMPTS = [3, 5, 10];
const LOCK_MINUTES = [1, 5, 15, 30];
const withCurrent = (list: number[], cur: number) => (list.includes(cur) ? list : [...list, cur]);
const fmt = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

const HOST_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$/; // same rule as the backend

export default function SettingsPage() {
  const windows = useWindows();
  const { theme, setTheme } = useTheme();
  const { hostName, setHostName } = useHost();
  const { t, lang, setLang } = useT();
  const fieldSize = useFieldSize();
  const [hostDraft, setHostDraft] = useState<string | null>(null); // null: show the saved name
  const hostValue = hostDraft ?? hostName;
  const hostValid = HOST_NAME_RE.test(hostValue.trim());
  const { fieldStyle } = usePdsConfig();

  const [remote, setRemote] = useState<RemoteSettings | null>(null);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);

  // Theme and field style are also saved on the server (eden.json), because the login page on remote devices cannot read
  // this browser's storage. First visit: push what this browser already uses.
  const saveAppearance = (patch: { theme?: string; field_style?: string; language?: string }) => {
    apiPost("/appearance", patch).catch((e) => setError(String(e)));
  };
  useEffect(() => {
    apiGet<{ theme: string | null; field_style: string | null }>("/appearance")
      .then((a) => {
        if (!a.theme || !a.field_style) saveAppearance({ theme: a.theme ?? theme, field_style: a.field_style ?? fieldStyle });
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const accept = (r: RemoteSettings) => {
    setRemote(r);
    setFetchedAt(Date.now());
  };
  usePoll(() => {
    apiGet<RemoteSettings>("/settings").then(accept).catch((e) => setError(String(e)));
  }, 5000);
  // One-second tick so the countdown moves between polls.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const call = async (run: () => Promise<RemoteSettings>, doneMsg: string) => {
    setBusy(true);
    setError(null);
    try {
      accept(await run());
      toast({ description: doneMsg });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const save = (patch: Partial<Pick<RemoteSettings, "session_timeout_minutes" | "lockout_attempts" | "lockout_minutes">>) => {
    if (!remote) return;
    const body = {
      session_timeout_minutes: remote.session_timeout_minutes,
      lockout_attempts: remote.lockout_attempts,
      lockout_minutes: remote.lockout_minutes,
      ...patch,
    };
    call(() => apiPost<RemoteSettings>("/settings", body), t("settings.saved"));
  };

  const saveHost = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<{ host_name: string }>("/host", { host_name: hostValue.trim() });
      setHostName(r.host_name);
      setHostDraft(null);
      toast({ description: t("settings.hostSaved") });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    setError(null);
    try {
      await apiPost<{ ok: boolean }>("/restart");
      setRestarting(true);
    } catch (e) {
      setError(String(e));
    }
  };
  const giveUpRestart = useCallback((reason: string) => {
    setRestarting(false);
    setError(reason);
  }, []);

  const enroll = remote?.enroll;
  const remaining = enroll ? Math.max(0, enroll.window_remaining - Math.floor((now - fetchedAt) / 1000)) : 0;

  return (
    <PageStack>
      <h1 className="text-xl font-semibold mb-4">{t("settings.title")}</h1>

      <Card>
        <ItemGroup>
          <ToggleRow
            label={t("settings.languageTitle")}
            description={t("settings.languageDescription")}
            value={lang}
            onChange={(v) => {
              setLang(v as "en" | "it");
              saveAppearance({ language: v });
            }}
            options={[
              { value: "en", label: t("settings.languageEn") },
              { value: "it", label: t("settings.languageIt") },
            ]}
          />
          <ItemSeparator />
          <ToggleRow
            label={t("settings.themeTitle")}
            description={t("settings.themeDescription")}
            value={theme}
            onChange={(v) => {
              setTheme(v as "light" | "dark");
              saveAppearance({ theme: v });
            }}
            options={[
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
          <ItemSeparator />
          <ToggleRow
            label={t("settings.fieldStyleTitle")}
            description={t("settings.fieldStyleDescription")}
            value={fieldStyle}
            onChange={(v) => {
              setPdsConfig({ fieldStyle: v as "fill" | "outline" });
              saveAppearance({ field_style: v });
            }}
            options={[
              { value: "fill", label: "Fill" },
              { value: "outline", label: "Outline" },
            ]}
          />
          <ItemSeparator />
          <Item size="sm">
            <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
              <ItemTitle>Design System</ItemTitle>
              <ItemDescription style={{ display: "block", overflow: "visible", WebkitLineClamp: "none" }}>
                {t("settings.pdsDescription")}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <Tag variant="default">v.{__PDS_VERSION__}</Tag>
            </ItemActions>
          </Item>
        </ItemGroup>
      </Card>

      <h2 className="pt-4 text-sm font-semibold">{t("settings.computerTitle")}</h2>
      <Card>
        <ItemGroup>
          <Item size="sm">
            <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
              <ItemTitle>{t("settings.hostTitle")}</ItemTitle>
              <ItemDescription style={{ display: "block", overflow: "visible", WebkitLineClamp: "none" }}>
                {t("settings.hostDescription")}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              {/* The page sits on the "alternative" surface; fields belong on "base" */}
              <div data-pds-surface="base" style={{ display: "contents" }}>
                <Field
                  size={fieldSize}
                  label={t("common.name")}
                  value={hostValue}
                  maxLength={32}
                  state={hostValid ? "default" : "error"}
                  onChange={(e) => setHostDraft(e.target.value)}
                />
              </div>
              <Button variant="default" size="small" disabled={busy || !hostValid || hostValue.trim() === hostName} onClick={saveHost}>
                {t("common.save")}
              </Button>
            </ItemActions>
          </Item>
        </ItemGroup>
      </Card>

      <LiveSettings />

      <h2 className="pt-4 text-sm font-semibold">{t("settings.remoteTitle")}</h2>
      <p className="text-sm text-muted-foreground">
        {t("settings.remoteDescription")}
      </p>
      {remote && (
        <>
          <Card>
            <ItemGroup>
              <ToggleRow
                label={t("settings.timeoutTitle")}
                description={t("settings.timeoutDescription")}
                value={String(remote.session_timeout_minutes)}
                onChange={(v) => !busy && save({ session_timeout_minutes: Number(v) })}
                options={withCurrent(TIMEOUTS, remote.session_timeout_minutes).map((n) => ({ value: String(n), label: n === 0 ? t("settings.never") : String(n) }))}
              />
              <ItemSeparator />
              <ToggleRow
                label={t("settings.attemptsTitle")}
                description={t("settings.attemptsDescription")}
                value={String(remote.lockout_attempts)}
                onChange={(v) => !busy && save({ lockout_attempts: Number(v) })}
                options={withCurrent(ATTEMPTS, remote.lockout_attempts).map((n) => ({ value: String(n), label: String(n) }))}
              />
              <ItemSeparator />
              <ToggleRow
                label={t("settings.lockTitle")}
                description={t("settings.lockDescription")}
                value={String(remote.lockout_minutes)}
                onChange={(v) => !busy && save({ lockout_minutes: Number(v) })}
                options={withCurrent(LOCK_MINUTES, remote.lockout_minutes).map((n) => ({ value: String(n), label: String(n) }))}
              />
              <ItemSeparator />
              <Item size="sm">
                <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
                  <ItemTitle>{t("settings.portTitle")}</ItemTitle>
                  <ItemDescription style={{ display: "block", overflow: "visible", WebkitLineClamp: "none" }}>
                    {t(windows ? "settings.portDescription.win" : "settings.portDescription", { host: hostName })}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <Tag variant="default">{remote.remote_port ?? "?"}</Tag>
                </ItemActions>
              </Item>
            </ItemGroup>
          </Card>
          {remote.session_timeout_minutes === 0 && (
            <Alert>
              <AlertDescription>{t("settings.neverAlert")}</AlertDescription>
            </Alert>
          )}

          <h2 className="pt-4 text-sm font-semibold">{t("settings.totpTitle")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("settings.totpDescription", { minutes: enroll?.window_minutes ?? 10 })}
          </p>
          {enroll?.enrolled && <p className="text-sm text-muted-foreground">{t("settings.configured")}</p>}
          {enroll && !enroll.enrolled && remaining > 0 && (
            <Card className="p-2 space-y-1">
              <div style={{ fontSize: "2rem", fontWeight: 600 }}>{fmt(remaining)}</div>
              <Progress value={(remaining / (enroll.window_minutes * 60)) * 100} aria-label={t("settings.timeLeft")} />
              <p className="text-sm">
                {t("settings.enrollOpen", { url: enroll.url ?? t("settings.enrollUrlFallback") })}
              </p>
              {remaining < 60 && <p className="text-sm font-semibold">{t("settings.hurry")}</p>}
              <Button variant="default" size="small" disabled={busy} onClick={() => call(() => apiPost<RemoteSettings>("/enroll/cancel"), t("settings.windowClosed"))}>
                {t("settings.closeWindow")}
              </Button>
            </Card>
          )}
          {enroll && !enroll.enrolled && remaining === 0 && (
            <Alert variant="destructive">
              <AlertDescription>{t("settings.notConfigured")}</AlertDescription>
            </Alert>
          )}
          {enroll && (enroll.enrolled || remaining === 0) && (
            <Confirm
              title={enroll.enrolled ? t("settings.resetTitle") : t("settings.openTitle")}
              description={t("settings.enrollConfirm", { minutes: enroll.window_minutes })}
              actionLabel={t("common.continue")}
              destructive
              onConfirm={() => call(() => apiPost<RemoteSettings>("/enroll/open"), t("settings.windowOpened"))}
              trigger={(open) => (
                <Button variant="destructive" size="small" disabled={busy || !enroll.remote_running} onClick={open}>
                  {enroll.enrolled ? t("settings.resetAction") : t("settings.openAction", { minutes: enroll.window_minutes })}
                </Button>
              )}
            />
          )}
          {enroll && !enroll.remote_running && <p className="text-xs text-muted-foreground">{t("settings.vpnNeeded")}</p>}
        </>
      )}
      {remote && (
        <>
          <h2 className="pt-4 text-sm font-semibold">{t("settings.edenTitle")}</h2>
          <Card>
            <ItemGroup>
              <Item size="sm">
                <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
                  <ItemTitle>{t("settings.restartTitle")}</ItemTitle>
                  <ItemDescription style={{ display: "block", overflow: "visible", WebkitLineClamp: "none" }}>
                    {t("settings.restartDescription")}
                    {remote.restart_available === false && t("settings.restartUnavailable")}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <Confirm
                    destructive
                    title={t("settings.restartConfirmTitle")}
                    description={t("settings.restartConfirmDescription")}
                    actionLabel={t("settings.restartAction")}
                    onConfirm={restart}
                    trigger={(open) => (
                      <Button variant="destructive" size="small" disabled={busy || !remote.restart_available} onClick={open}>
                        <RotateCw /> {t("settings.restartTitle")}
                      </Button>
                    )}
                  />
                </ItemActions>
              </Item>
            </ItemGroup>
          </Card>
        </>
      )}
      <Feedback error={error} />
      {restarting && <RestartOverlay onGiveUp={giveUpRestart} />}
    </PageStack>
  );
}
