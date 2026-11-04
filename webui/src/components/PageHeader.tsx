// Title, optional subtitle and an optional action on the right. Built on the PDS layout primitives: the Row wraps
// by itself on a phone (PDS sets --pds-row-wrap), so the action drops under the title instead of overflowing.
// Shared by the pages that have a header action (Servizi, Dispositivi); the others use a plain title.
import type { ReactNode } from "react";
import { Row, Stack } from "@workspace/pds/components/ui/layout";

export default function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <Row gap="s" className="justify-between">
      <Stack gap="sss">
        <h1 className="text-xl font-semibold">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </Stack>
      {action}
    </Row>
  );
}
