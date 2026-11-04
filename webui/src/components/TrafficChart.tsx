// Meshnet traffic over a chosen range (data from the server's stored history), with a dot on the line each time a
// device came online (blue) or went offline (grey). Hover (or tap) a dot to read what happened. Loaded only with the
// Home page, like the chart library it uses.
import { useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceDot, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@workspace/pds/components/ui/chart";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { Toggle } from "@workspace/pds/components/ui/toggle";
import { translate, useT } from "../lib/i18n";
import { formatRate, RANGE_OPTIONS, type HistoryData, type HistoryEvent, type RangeId } from "../lib/monitor";

// --chart-N are HSL triplets in PDS, hence hsl(var(...)). The names are what the tooltip and the legend show.
const chartColors = { rx: "hsl(var(--chart-1))", tx: "hsl(var(--chart-2))" };
const CONNECT_COLOR = "#2563eb";
const DISCONNECT_COLOR = "#9ca3af";
const TIP_HALF_WIDTH = 130; // px: half of the dot tooltip's width, to keep it inside the chart

const hhmm = (t: number, locale: string) => new Date(t * 1000).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
const dayHhmm = (t: number, locale: string) =>
  new Date(t * 1000).toLocaleString(locale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const full = (t: number, locale: string) => new Date(t * 1000).toLocaleString(locale);

function duration(s: number): string {
  if (s < 90) return translate("duration.seconds", { n: Math.max(1, Math.round(s)) });
  if (s < 5400) return translate("duration.minutes", { n: Math.round(s / 60) });
  if (s < 129600) return translate("duration.hours", { n: Math.round(s / 3600) });
  return translate("duration.days", { n: Math.round(s / 86400) });
}

type Tip = { ev: HistoryEvent; x: number; y: number };

export default function TrafficChart({
  data,
  range,
  onRange,
}: {
  data: HistoryData | null;
  range: RangeId;
  onRange: (r: RangeId) => void;
}) {
  const { t, locale } = useT();
  const chartConfig: ChartConfig = {
    rx: { label: t("chart.in"), color: chartColors.rx },
    tx: { label: t("chart.out"), color: chartColors.tx },
  };
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  const rows = useMemo(() => (data ? data.points.map(([t, rx, tx]) => ({ t, rx, tx })) : []), [data]);
  // Each event sits on the line: at the higher of the two rates of the nearest sample (0 where there is none).
  const dots = useMemo(() => {
    if (!data || data.points.length === 0) return [];
    return data.events.map((ev) => {
      let best = data.points[0];
      for (const p of data.points) if (Math.abs(p[0] - ev.t) < Math.abs(best[0] - ev.t)) best = p;
      return { ev, y: Math.max(best[1] ?? 0, best[2] ?? 0) };
    });
  }, [data]);

  const long = range === "48h" || range === "7d" || (range === "all" && data !== null && data.to - data.from > 86400);
  const tickFormat = (ts: number) => (long ? dayHhmm(ts, locale) : hhmm(ts, locale));
  const showTip = (ev: HistoryEvent, target: Element) => {
    const b = box.current?.getBoundingClientRect();
    const r = target.getBoundingClientRect();
    if (!b) return;
    const width = b.width;
    const x = Math.min(Math.max(r.left + r.width / 2 - b.left, TIP_HALF_WIDTH), Math.max(TIP_HALF_WIDTH, width - TIP_HALF_WIDTH));
    setTip({ ev, x, y: r.top - b.top });
  };

  return (
    <div>
      <div style={{ marginBottom: "0.75rem" }}>
        {/* Clicking the active item yields an empty value: ignored, one range stays selected */}
        <Toggle type="single" size="sm" value={range} onValueChange={(v: string) => v && onRange(v as RangeId)}>
          {RANGE_OPTIONS.map((o) => (
            <Toggle asItem key={o.value} value={o.value}>
              {t(o.label)}
            </Toggle>
          ))}
        </Toggle>
      </div>

      {!data ? (
        <Spinner />
      ) : rows.length < 2 ? (
        <p className="text-sm text-muted-foreground">{t("chart.collecting")}</p>
      ) : (
        <div ref={box} style={{ position: "relative" }} onMouseLeave={() => setTip(null)}>
          <ChartContainer config={chartConfig} style={{ height: "14rem", width: "100%" }}>
            <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="linear"
                domain={[data.from, data.to]}
                allowDataOverflow
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={long ? 72 : 48}
                tickFormatter={tickFormat}
              />
              <YAxis tickLine={false} axisLine={false} width={76} tickFormatter={(v: number) => formatRate(v)} />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    indicator="line"
                    labelFormatter={(_l, payload) => {
                      const ts = payload?.[0]?.payload?.t;
                      return typeof ts === "number" ? full(ts, locale) : "";
                    }}
                    formatter={(value, name) => (
                      <span>
                        {chartConfig[String(name)]?.label ?? String(name)}: {formatRate(Number(value))}
                      </span>
                    )}
                  />
                }
              />
              <Area dataKey="rx" type="monotone" stroke="var(--color-rx)" fill="var(--color-rx)" fillOpacity={0.2} isAnimationActive={false} />
              <Area dataKey="tx" type="monotone" stroke="var(--color-tx)" fill="var(--color-tx)" fillOpacity={0.2} isAnimationActive={false} />
              {dots.map(({ ev, y }) => (
                <ReferenceDot
                  key={`${ev.t}-${ev.name}-${ev.kind}`}
                  x={ev.t}
                  y={y}
                  ifOverflow="visible"
                  isFront
                  shape={(p: { cx?: number; cy?: number }) => (
                    <g
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(e) => showTip(ev, e.currentTarget)}
                      onClick={(e) => (tip && tip.ev === ev ? setTip(null) : showTip(ev, e.currentTarget))}
                    >
                      <circle cx={p.cx} cy={p.cy} r={11} fill="transparent" />
                      <circle
                        cx={p.cx}
                        cy={p.cy}
                        r={5}
                        fill={ev.kind === "connect" ? CONNECT_COLOR : DISCONNECT_COLOR}
                        stroke="hsl(var(--background))"
                        strokeWidth={2}
                      />
                    </g>
                  )}
                />
              ))}
              <ChartLegend content={<ChartLegendContent />} />
            </AreaChart>
          </ChartContainer>
          {tip && (
            <div
              role="tooltip"
              className="rounded-md border bg-background text-xs shadow-md"
              style={{
                position: "absolute",
                left: tip.x,
                top: tip.y,
                transform: "translate(-50%, calc(-100% - 8px))",
                width: "max-content",
                maxWidth: 2 * TIP_HALF_WIDTH,
                padding: "0.5rem 0.625rem",
                pointerEvents: "none",
                zIndex: 10,
              }}
            >
              <div className="font-semibold">
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    marginRight: 6,
                    background: tip.ev.kind === "connect" ? CONNECT_COLOR : DISCONNECT_COLOR,
                  }}
                />
                {tip.ev.kind === "connect" ? t("chart.connected", { name: tip.ev.name ?? t("chart.deviceFallback") }) : t("chart.disconnected", { name: tip.ev.name ?? t("chart.deviceFallback") })}
              </div>
              <div className="text-muted-foreground">{full(tip.ev.t, locale)}</div>
              {tip.ev.ip && <div className="text-muted-foreground">{tip.ev.ip}</div>}
              {tip.ev.untrusted && <div>{t("chart.untrustedDevice")}</div>}
              <div className="text-muted-foreground">
                {tip.ev.kind === "connect" ? t("chart.wasOffline", { duration: duration(tip.ev.after_s) }) : t("chart.wasOnline", { duration: duration(tip.ev.after_s) })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
