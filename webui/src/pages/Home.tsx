// The landing page: a live monitor of what is happening on Meshnet. It is loaded lazily (App.tsx), so the chart library
// is not even downloaded unless this page is opened. Its data hooks (lib/monitor.ts) poll only while the page is mounted,
// the tab is visible and the "Live traffic" switch (subheader) is on; with it off the page asks for nothing.
// The chart shows the history kept by the server, for the chosen range.
import { useMemo, useState } from "react";
import { Badge } from "@workspace/pds/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@workspace/pds/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@workspace/pds/components/ui/empty";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { Tag } from "@workspace/pds/components/ui/tag";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@workspace/pds/components/ui/table";
import Feedback from "../components/Feedback";
import Logo from "../components/Logo";
import TrafficChart from "../components/TrafficChart";
import { useHost } from "../lib/host";
import { useT } from "../lib/i18n";
import { useLive } from "../lib/live";
import { formatBytes, formatRate, useHistory, useMonitor, type Peer, type RangeId, type Row as ConnRow } from "../lib/monitor";

const fullRow = { gridColumn: "1 / -1" } as const;
const num = { textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" } as const;

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader style={{ padding: "1rem" }}>
        <CardDescription>{label}</CardDescription>
        <CardTitle style={{ fontSize: "1.5rem", lineHeight: 1.2, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{value}</CardTitle>
        {hint && <CardDescription>{hint}</CardDescription>}
      </CardHeader>
    </Card>
  );
}

function PeerLine({ peer, muted }: { peer: Peer; muted?: boolean }) {
  const { t } = useT();
  return (
    <Row gap="ss" className="justify-between">
      <Row gap="ss">
        <Badge variant={peer.online ? "ready" : "disabled"} aria-hidden="true" />
        <span className={muted ? "text-sm text-muted-foreground" : "text-sm"}>{peer.name}</span>
        {peer.untrusted && <Tag variant="alert">{t("tag.untrusted")}</Tag>}
        {peer.enabled === false && <span className="text-xs text-muted-foreground">{t("peer.disabled")}</span>}
      </Row>
      <span className="text-xs text-muted-foreground" title={peer.status ?? undefined}>
        {peer.online ? t("peer.online") : t("peer.offline")}
        {peer.ip ? ` · ${peer.ip}` : ""}
      </span>
    </Row>
  );
}

export default function Home() {
  const { t, locale } = useT();
  const { hostName } = useHost();
  const { info } = useLive();
  const live = info?.live === true;
  const refreshS = info?.refresh_seconds ?? 2;
  const { snap, rows, history, devices, error } = useMonitor(live, refreshS * 1000, (info?.presence_seconds ?? 15) * 1000);
  const [range, setRange] = useState<RangeId>("all");
  const { data: chartData, error: chartError } = useHistory(range, live, refreshS * 1000);

  // Address -> name, from the Nord peer list (configured devices first, then peers Eden does not know).
  const names = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of [...(devices?.unknown ?? []), ...(devices?.devices ?? [])]) if (p.ip) m.set(p.ip, p.name);
    return m;
  }, [devices]);
  const nameOf = (ip: string) => (ip === snap?.mesh_ip ? hostName : names.get(ip) ?? ip);
  // Addresses of untrusted devices, to tag their connections in the table.
  const untrustedIps = useMemo(() => {
    const s = new Set<string>();
    for (const p of [...(devices?.unknown ?? []), ...(devices?.devices ?? [])]) if (p.ip && p.untrusted) s.add(p.ip);
    return s;
  }, [devices]);
  const describe = (c: ConnRow) =>
    c.direction === "out"
      ? t("home.connOut", { port: c.remote_port })
      : c.kind === "remote"
        ? t("home.connRemote")
        : c.kind === "service"
          ? c.service ?? ""
          : t("home.connPort", { port: c.local_port });

  const last = history[history.length - 1];
  const online = devices?.devices.filter((d) => d.online).length;
  const up = snap?.vpn_up === true;

  return (
    <>
      <div style={fullRow}>
        {/* A plain flex div, not a Row (decision 38): logo and title stay side by side on a phone */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {/* The logo still fades in, now as the header of the monitor */}
          <div className="eden-fade-in">
            <Logo size={56} />
          </div>
          <Stack gap="sss">
            <h1 className="text-xl font-semibold">{t("home.title")}</h1>
            <p className="text-sm text-muted-foreground">
              {!live
                ? t("home.subtitleOff")
                : up
                  ? t("home.subtitleLive", {
                      every: refreshS === 1 ? t("home.every.one") : t("home.every.other", { n: refreshS }),
                      when: info?.record_when_closed ? t("home.whenClosed") : t("home.whenOpen"),
                    })
                  : t("home.subtitleRealtime")}
            </p>
          </Stack>
        </div>
      </div>

      {live && (error ?? chartError) && (
        <div style={fullRow}>
          <Feedback error={error ?? chartError} />
        </div>
      )}

      {info && !live && (
        <div style={fullRow}>
          <Empty>
            <EmptyHeader>
              <EmptyTitle>{t("home.offTitle")}</EmptyTitle>
              <EmptyDescription>{t("home.offDescription")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </div>
      )}

      {live && !snap && !error && (
        <div style={fullRow}>
          <Spinner />
        </div>
      )}

      {live && snap && !up && (
        <div style={fullRow}>
          <Empty>
            <EmptyHeader>
              <EmptyTitle>{t("home.vpnOffTitle")}</EmptyTitle>
              <EmptyDescription>{t("home.vpnOffDescription")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </div>
      )}

      {live && snap && up && (
        <>
          {/* Four tiles: two per row on a phone, four on a wide page (auto-fit decides) */}
          <div style={{ ...fullRow, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9.5rem, 1fr))", gap: "var(--canvas-gap)" }}>
            <Tile label={t("home.tileIn")} value={last ? formatRate(last.rx) : "…"} hint={t("home.tileTo", { host: hostName })} />
            <Tile label={t("home.tileOut")} value={last ? formatRate(last.tx) : "…"} hint={t("home.tileFrom", { host: hostName })} />
            <Tile label={t("home.tileConnections")} value={String(rows.length)} hint={snap.connections === null ? t("home.tileUnreadable") : t("home.tileOpen")} />
            <Tile label={t("home.tileDevices")} value={online === undefined ? "…" : `${online} / ${devices?.devices.length ?? 0}`} hint={t("home.tileOnline")} />
          </div>

          <Card style={fullRow}>
            <CardHeader>
              <CardTitle>{t("home.chartTitle")}</CardTitle>
              <CardDescription>
                {t("home.chartDescription")}
                {range === "all" && chartData?.since ? t("home.chartSince", { date: new Date(chartData.since * 1000).toLocaleString(locale) }) : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TrafficChart data={chartData} range={range} onRange={setRange} />
            </CardContent>
          </Card>

          <Card style={fullRow}>
            <CardHeader>
              <CardTitle>{t("home.connTitle")}</CardTitle>
              <CardDescription>{t("home.connDescription", { host: hostName })}</CardDescription>
            </CardHeader>
            <CardContent>
              {snap.connections === null ? (
                <p className="text-sm text-muted-foreground">{t("home.connUnreadable")}</p>
              ) : rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("home.connNone")}</p>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("home.colDevice")}</TableHead>
                        <TableHead style={num}>{t("home.colReceived")}</TableHead>
                        <TableHead style={num}>{t("home.colSent")}</TableHead>
                        <TableHead style={num}>{t("home.colTotal")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((c) => (
                        <TableRow
                          key={c.id}
                          title={`${c.remote_ip}:${c.remote_port}${c.rtt_ms !== null ? t("home.rowTitleRtt", { ms: c.rtt_ms }) : ""}${c.idle_ms !== null ? t("home.rowTitleIdle", { s: Math.round(c.idle_ms / 1000) }) : ""}`}
                        >
                          <TableCell>
                            <div className="text-sm">
                              {nameOf(c.remote_ip)} {untrustedIps.has(c.remote_ip) && <Tag variant="alert">{t("tag.untrusted")}</Tag>}
                            </div>
                            <div className="text-xs text-muted-foreground">{describe(c)}</div>
                          </TableCell>
                          <TableCell style={num}>{formatRate(c.rate_received)}</TableCell>
                          <TableCell style={num}>{formatRate(c.rate_sent)}</TableCell>
                          <TableCell style={num}>{formatBytes(c.bytes_sent + c.bytes_received)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              {snap.truncated && <p className="text-xs text-muted-foreground">{t("home.connTruncated")}</p>}
            </CardContent>
          </Card>

          <Card style={fullRow}>
            <CardHeader>
              <CardTitle>{t("home.devicesTitle")}</CardTitle>
              <CardDescription>{t("home.devicesDescription", { s: info?.presence_seconds ?? 15 })}</CardDescription>
            </CardHeader>
            <CardContent>
              {!devices ? (
                <Spinner />
              ) : devices.peers_ok === false ? (
                <p className="text-sm text-muted-foreground">{t("home.peersUnreadable")}</p>
              ) : (
                <Stack gap="ss">
                  {devices.devices.map((d) => (
                    <PeerLine key={d.name} peer={d} />
                  ))}
                  {devices.unknown.length > 0 && (
                    <>
                      <p className="text-xs text-muted-foreground">{t("home.otherPeers")}</p>
                      {devices.unknown.map((d) => (
                        <PeerLine key={`${d.name}-${d.ip}`} peer={d} muted />
                      ))}
                    </>
                  )}
                </Stack>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}
