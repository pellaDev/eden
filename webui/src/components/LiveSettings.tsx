// Settings of the Live traffic scan: how often it reads, how often it checks the devices, how long the history is kept,
// and whether it keeps recording while no Eden page is open. The on/off switch itself is in the subheader.
import { useEffect, useState } from "react";
import { Button } from "@workspace/pds/components/ui/button";
import { Card } from "@workspace/pds/components/ui/card";
import { Field } from "@workspace/pds/components/ui/field";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemSeparator, ItemTitle } from "@workspace/pds/components/ui/item";
import { toast } from "@workspace/pds/hooks/use-toast";
import { useT } from "../lib/i18n";
import { useLive } from "../lib/live";
import { useFieldSize } from "../lib/useFieldSize";
import Feedback from "./Feedback";
import OnOff from "./OnOff";

const wide = { display: "block", overflow: "visible", WebkitLineClamp: "none" } as const; // ItemDescription clamps to 2 lines
const grow = { flex: "1 1 16rem", minWidth: 0 } as const;
// Same limits as the backend (MONITOR_LIMITS).
const LIMITS = { refresh: [1, 60], presence: [5, 300], retention: [1, 35] } as const;
const valid = (text: string, [lo, hi]: readonly [number, number]) => /^\d{1,4}$/.test(text.trim()) && Number(text) >= lo && Number(text) <= hi;

export default function LiveSettings() {
  const { t, locale } = useT();
  const { info, busy, error, saveSettings } = useLive();
  const fieldSize = useFieldSize();
  const [refresh, setRefresh] = useState("");
  const [presence, setPresence] = useState("");
  const [retention, setRetention] = useState("");
  const [closed, setClosed] = useState(true);
  const [loaded, setLoaded] = useState(false);

  // The form starts from the saved values once, when they first arrive; the periodic refresh of `info` never overwrites typing.
  useEffect(() => {
    if (info && !loaded) {
      setRefresh(String(info.refresh_seconds));
      setPresence(String(info.presence_seconds));
      setRetention(String(info.retention_days));
      setClosed(info.record_when_closed);
      setLoaded(true);
    }
  }, [info, loaded]);

  if (!info) return null;
  const ok = valid(refresh, LIMITS.refresh) && valid(presence, LIMITS.presence) && valid(retention, LIMITS.retention);
  const changed =
    Number(refresh) !== info.refresh_seconds ||
    Number(presence) !== info.presence_seconds ||
    Number(retention) !== info.retention_days ||
    closed !== info.record_when_closed;
  const state = (text: string, lim: readonly [number, number]) => (valid(text, lim) ? "default" : "error");

  const save = async () => {
    const done = await saveSettings({
      refresh_seconds: Number(refresh),
      presence_seconds: Number(presence),
      retention_days: Number(retention),
      record_when_closed: closed,
    });
    if (done) toast({ description: t("liveSettings.saved") });
  };

  const row = (title: string, description: string, value: string, set: (v: string) => void, lim: readonly [number, number], unit: string) => (
    <Item size="sm">
      <ItemContent style={grow}>
        <ItemTitle>{title}</ItemTitle>
        <ItemDescription style={wide}>{description}</ItemDescription>
      </ItemContent>
      <ItemActions>
        {/* The page sits on the "alternative" surface; fields belong on "base" */}
        <div data-pds-surface="base" style={{ display: "contents" }}>
          <Field
            size={fieldSize}
            label={unit}
            type="number"
            inputMode="numeric"
            min={lim[0]}
            max={lim[1]}
            value={value}
            state={state(value, lim)}
            onChange={(e) => set(e.target.value)}
          />
        </div>
      </ItemActions>
    </Item>
  );

  return (
    <>
      <h2 className="pt-4 text-sm font-semibold">{t("liveSettings.title")}</h2>
      <p className="text-sm text-muted-foreground">{t("liveSettings.intro")}</p>
      <Card>
        <ItemGroup>
          {row(t("liveSettings.refreshTitle"), t("liveSettings.refreshDescription"), refresh, setRefresh, LIMITS.refresh, t("liveSettings.refreshUnit"))}
          <ItemSeparator />
          {row(t("liveSettings.presenceTitle"), t("liveSettings.presenceDescription"), presence, setPresence, LIMITS.presence, t("liveSettings.presenceUnit"))}
          <ItemSeparator />
          {row(t("liveSettings.retentionTitle"), t("liveSettings.retentionDescription"), retention, setRetention, LIMITS.retention, t("liveSettings.retentionUnit"))}
          <ItemSeparator />
          <Item size="sm">
            <ItemContent style={grow}>
              <ItemTitle>{t("liveSettings.closedTitle")}</ItemTitle>
              <ItemDescription style={wide}>{t("liveSettings.closedDescription")}</ItemDescription>
            </ItemContent>
            <ItemActions>
              <OnOff label={t("liveSettings.closedTitle")} value={closed} disabled={busy} onChange={setClosed} />
            </ItemActions>
          </Item>
          <ItemSeparator />
          <Item size="sm">
            <ItemContent style={grow}>
              <ItemDescription style={wide}>
                {info.since
                  ? t("liveSettings.history", { minutes: info.minutes, date: new Date(info.since * 1000).toLocaleString(locale), events: info.events })
                  : t("liveSettings.historyEmpty")}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <Button variant="default" size="small" disabled={busy || !ok || !changed} onClick={save}>
                {t("common.save")}
              </Button>
            </ItemActions>
          </Item>
        </ItemGroup>
      </Card>
      <Feedback error={error} />
    </>
  );
}
