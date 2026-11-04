// VPN group: Nord daemon, Meshnet interface, eden_remote.
import { Fragment, useCallback, useEffect, useState } from "react";
import { Button } from "@workspace/pds/components/ui/button";
import { Badge } from "@workspace/pds/components/ui/badge";
import { Card } from "@workspace/pds/components/ui/card";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
} from "@workspace/pds/components/ui/item";
import { toast } from "@workspace/pds/hooks/use-toast";
import { Row } from "@workspace/pds/components/ui/layout";
import { apiGet, apiPost } from "../lib/api";
import { usePoll } from "../lib/usePoll";
import Confirm from "../components/Confirm";
import Feedback from "../components/Feedback";
import PageLoading from "../components/PageLoading";
import PageStack from "../components/PageStack";
import StatusRow from "../components/StatusRow";
import { useT } from "../lib/i18n";

type VpnState = { daemon: boolean; iface: boolean; remote: boolean; remote_url: string | null };
type Setting = { name: string; value: string };
type OpResult = { ok: boolean; stdout: string; stderr: string };

// Last lines of a command's output: enough to see why it failed.
const tail = (s: string, n = 8) => s.trim().split("\n").slice(-n).join("\n");

export default function Vpn() {
  const { t } = useT();
  const [state, setState] = useState<VpnState | null>(null);
  const [settings, setSettings] = useState<Setting[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadState = useCallback(
    () => apiGet<VpnState>("/vpn").then(setState).catch((e) => setError(String(e))),
    [],
  );
  const loadSettings = useCallback(
    () => apiGet<{ settings: Setting[] | null }>("/vpn/settings").then((r) => setSettings(r.settings)).catch(() => setSettings(null)),
    [],
  );
  usePoll(loadState, 5000);
  useEffect(() => {
    loadSettings();
  }, [state?.daemon, loadSettings]);

  const run = async (path: string, doneMsg: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<OpResult>(path);
      if (r.ok) toast({ description: doneMsg });
      else setError(tail(r.stderr || r.stdout || t("common.operationFailed")));
    } catch (e) {
      setError(String(e));
    } finally {
      await loadState();
      loadSettings();
      setBusy(false);
    }
  };

  if (!state) return <PageLoading title={t("vpn.title")} error={error} />;

  const allUp = state.daemon && state.iface && state.remote;
  const allDown = !state.daemon && !state.iface && !state.remote;

  return (
    <PageStack>
      <h1 className="text-xl font-semibold">{t("vpn.title")}</h1>
      <Card>
        <ItemGroup>
          <StatusRow label={t("vpn.daemon")} on={state.daemon} />
          <ItemSeparator />
          <StatusRow label={t("vpn.iface")} on={state.iface} />
          <ItemSeparator />
          <StatusRow label={t("vpn.remote")} on={state.remote} />
          {state.remote_url && (
            <>
              <ItemSeparator />
              <Item size="sm">
                <ItemContent>
                  <ItemDescription>{state.remote_url}</ItemDescription>
                </ItemContent>
              </Item>
            </>
          )}
        </ItemGroup>
      </Card>

      <Row gap="ss" className="py-2">
        <Button variant="default" size="small" disabled={busy || allUp} onClick={() => run("/vpn/up", t("vpn.upDone"))}>
          {t("vpn.up")}
        </Button>
        <Confirm
          title={t("vpn.downTitle")}
          description={t("vpn.downDescription")}
          actionLabel={t("vpn.down")}
          destructive
          onConfirm={() => run("/vpn/down", t("vpn.downDone"))}
          trigger={(open) => (
            <Button variant="destructive" size="small" disabled={busy || allDown} onClick={open}>
              {t("vpn.down")}
            </Button>
          )}
        />
      </Row>
      <Feedback busy={busy} error={error} />

      <h2 className="pt-4 text-sm font-semibold">{t("vpn.settingsTitle")}</h2>
      {settings === null && <p className="text-sm text-muted-foreground">{t("vpn.settingsUnavailable")}</p>}
      {settings && settings.length > 0 && (
        <Card>
          <ItemGroup>
            {settings.map((s, i) => (
              <Fragment key={s.name}>
                {i > 0 && <ItemSeparator />}
                <Item size="sm">
                  <ItemContent>
                    <ItemTitle>{s.name}</ItemTitle>
                  </ItemContent>
                  <ItemActions>
                    <Badge variant={s.value === "disabled" ? "ready" : "error"} aria-hidden="true" />
                    <span className="text-sm text-muted-foreground">
                      {s.value}{s.value === "disabled" ? "" : `  ${t("vpn.expected")}`}
                    </span>
                  </ItemActions>
                </Item>
              </Fragment>
            ))}
          </ItemGroup>
        </Card>
      )}
    </PageStack>
  );
}
