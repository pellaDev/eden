// State of the last action on a page: "busy" line and the backend error (shown verbatim, it stays visible).
// Success confirmations are toasts (see the pages), not shown here.
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { useT } from "../lib/i18n";

export default function Feedback({ busy, error }: { busy?: boolean; error?: string | null }) {
  const { t } = useT();
  return (
    <>
      {busy && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          <span>{t("feedback.busy")}</span>
        </div>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription style={{ whiteSpace: "pre-wrap" }}>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}
