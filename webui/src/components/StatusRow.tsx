// One process/daemon state line. The PDS "simple" Badge is only a dot, so the word carries the meaning.
import { Badge } from "@workspace/pds/components/ui/badge";
import { Item, ItemActions, ItemContent, ItemTitle } from "@workspace/pds/components/ui/item";
import { useT } from "../lib/i18n";

export default function StatusRow({ label, on }: { label: string; on: boolean }) {
  const { t } = useT();
  return (
    <Item size="sm">
      <ItemContent>
        <ItemTitle>{label}</ItemTitle>
      </ItemContent>
      <ItemActions>
        <Badge variant={on ? "ready" : "disabled"} aria-hidden="true" />
        <span className={on ? "text-sm" : "text-sm text-muted-foreground"}>{on ? t("common.active") : t("common.stopped")}</span>
      </ItemActions>
    </Item>
  );
}
