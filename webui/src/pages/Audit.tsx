// Read-only audit view: the root helper's journal entries and every log in data/logs/.
// The log source is a Tabs selector; "Actions only" hides the polling GETs of eden_local's access log.
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@workspace/pds/components/ui/button";
import { Row } from "@workspace/pds/components/ui/layout";
import { Card } from "@workspace/pds/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader } from "@workspace/pds/components/ui/empty";
import { ScrollArea } from "@workspace/pds/components/ui/scroll-area";
import { Switch } from "@workspace/pds/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@workspace/pds/components/ui/tabs";
import { Toggle } from "@workspace/pds/components/ui/toggle";
import { apiGet } from "../lib/api";
import Feedback from "../components/Feedback";
import PageStack from "../components/PageStack";
import { useT } from "../lib/i18n";

type Source = { id: string; label: string };
type AuditResult = { source: string; lines: string[] };

const LINE_OPTIONS = [100, 200, 500];

export default function Audit() {
  const { t } = useT();
  const [sources, setSources] = useState<Source[]>([]);
  const [source, setSource] = useState("helper");
  const [lines, setLines] = useState(200);
  const [actionsOnly, setActionsOnly] = useState(false);
  const [result, setResult] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0); // ignore a slow response that arrives after the selection changed

  useEffect(() => {
    apiGet<{ sources: Source[] }>("/audit/sources").then((r) => setSources(r.sources)).catch((e) => setError(String(e)));
  }, []);

  const load = useCallback(() => {
    const mine = ++seq.current;
    const q = `source=${encodeURIComponent(source)}&lines=${lines}&actions_only=${actionsOnly && source === "eden_local"}`;
    apiGet<AuditResult>(`/audit?${q}`)
      .then((r) => {
        if (mine === seq.current) {
          setResult(r.lines);
          setError(null);
        }
      })
      .catch((e) => mine === seq.current && setError(String(e)));
  }, [source, lines, actionsOnly]);

  useEffect(() => {
    load();
    const id = setInterval(() => {
      if (!document.hidden) load();
    }, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <PageStack>
      <h1 className="text-xl font-semibold">{t("audit.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("audit.description")}</p>

      <Tabs value={source} onValueChange={setSource}>
        {/* PDS wraps the tab list only on a phone (--pds-row-wrap is nowrap on desktop). There is one log per managed
            process, so the list can be longer than the 40rem column: use PDS's own wrap value here too. */}
        <TabsList style={{ "--pds-row-wrap": "wrap" } as React.CSSProperties}>
          {sources.map((s) => (
            <TabsTrigger key={s.id} value={s.id}>
              {s.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* One panel for whichever source is selected: the content is the same view, only the query differs */}
        <TabsContent value={source} className="space-y-2">
          <Row gap="ss" className="py-1">
            {/* Exclusive choice with immediate effect: an empty value (clicking the active item) is ignored */}
            <Toggle type="single" size="sm" value={String(lines)} onValueChange={(v: string) => v && setLines(Number(v))}>
              {LINE_OPTIONS.map((n) => (
                <Toggle asItem key={n} value={String(n)}>
                  {t("audit.lines", { n })}
                </Toggle>
              ))}
            </Toggle>
            {source === "eden_local" && (
              <Switch label={t("audit.actionsOnly")} checked={actionsOnly} onChange={(e) => setActionsOnly(e.target.checked)} />
            )}
            <Button variant="default" size="small" onClick={load}>
              {t("audit.refresh")}
            </Button>
          </Row>

          <Feedback error={error} />
          {result && result.length === 0 && !error && (
            <Empty>
              <EmptyHeader>
                <EmptyDescription>{t("audit.empty")}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          {/* Card clips the corners; the ScrollArea grows with the log up to a cap (see eden.css), then scrolls */}
          {result && result.length > 0 && (
            <Card style={{ overflow: "hidden" }}>
              <ScrollArea type="auto" className="eden-scroll eden-scroll-capped">
                <div className="p-2 text-xs" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontFamily: "monospace" }}>
                  {[...result].reverse().join("\n")}
                </div>
              </ScrollArea>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </PageStack>
  );
}
