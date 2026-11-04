// What a remote device sees after a successful login: one icon per service that is really open to it (service on,
// granted to this device, device enabled), each opening in a new tab; at the bottom, the current state of this device
// (trusted or untrusted, as Eden and Meshnet have it right now). The data comes from Eden local through eden_remote,
// which looks the device up by the address of the connection, so the browser cannot ask about another device.
import { useCallback, useEffect, useState } from "react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Card } from "@workspace/pds/components/ui/card";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { Tag } from "@workspace/pds/components/ui/tag";
import NameAvatar from "../components/NameAvatar";
import { translate as t } from "../lib/i18n";
import { ApiError, getHome, type HomeData } from "./loginApi";

const REFRESH_MS = 15000;

export default function HomeDashboard({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [data, setData] = useState<HomeData | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getHome());
      setFailed(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onLoggedOut(); // the session ended: back to the login form
      else setFailed(true);
    }
  }, [onLoggedOut]);

  useEffect(() => {
    void load();
    const id = setInterval(() => {
      if (!document.hidden) void load();
    }, REFRESH_MS);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  if (!data) {
    return failed ? (
      <Alert variant="destructive">
        <AlertDescription>{t("login.homeError")}</AlertDescription>
      </Alert>
    ) : (
      <div style={{ display: "flex", justifyContent: "center", padding: "1rem" }}>
        <Spinner />
      </div>
    );
  }

  // A service is opened on the same address this page came from (Eden's Meshnet address), at its own port.
  const openUrl = (port: number) => `http://${window.location.hostname}:${port}/`;
  const device = data.device;

  return (
    <Stack gap="m">
      <p className="text-sm text-muted-foreground" style={{ textAlign: "center" }}>
        {t("login.homeSubtitle", { host: data.host_name })}
      </p>
      {failed && (
        <Alert variant="destructive">
          <AlertDescription>{t("login.homeError")}</AlertDescription>
        </Alert>
      )}
      {data.services.length === 0 ? (
        <p className="text-sm text-muted-foreground" style={{ textAlign: "center" }}>
          {device && device.known && !device.enabled ? t("login.deviceDisabled") : t("login.noServices")}
        </p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(6.5rem, 1fr))", gap: "1rem" }}>
          {data.services.map((s) => (
            <a
              key={s.name}
              href={openUrl(s.port)}
              target="_blank"
              rel="noopener noreferrer"
              title={s.note || s.name}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", textAlign: "center", textDecoration: "none", color: "inherit", minWidth: 0 }}
            >
              <NameAvatar name={s.name} src={s.avatar} size={64} outlined />
              <span className="text-sm" style={{ fontWeight: 600, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.name}
              </span>
              <span className="text-xs text-muted-foreground" style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: "-0.375rem" }}>
                {t("login.fromHost", { host: data.host_name })}
              </span>
            </a>
          ))}
        </div>
      )}
      <Card className="p-2">
        <Row gap="ss" className="justify-between">
          <Stack gap="ss">
            <span className="text-xs text-muted-foreground">{t("login.thisDevice")}</span>
            <span className="text-sm" style={{ fontWeight: 600 }}>
              {device ? device.name : t("login.unknownDevice")}
            </span>
          </Stack>
          <Tag variant={data.trusted ? "ready" : "alert"}>{data.trusted ? t("tag.trusted") : t("tag.untrusted")}</Tag>
        </Row>
      </Card>
    </Stack>
  );
}
