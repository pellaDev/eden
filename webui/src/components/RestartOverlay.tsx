// Modal shown while Eden restarts. The restart stops Eden local itself, so this page loses the server and must
// find it again: phase 1 waits until /api/status stops answering (the restart has really begun), phase 2 waits
// until it answers again (Eden local is the last thing "up" starts, so everything else is already back) and then
// reloads the page. If it never goes down, or never comes back, it gives up and tells the caller.
import { useEffect } from "react";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from "@workspace/pds/components/ui/alert-dialog";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { apiGet } from "../lib/api";
import { translate, useT } from "../lib/i18n";

const NEVER_WENT_DOWN_MS = 20_000;
const NEVER_CAME_BACK_MS = 180_000;

export default function RestartOverlay({ onGiveUp }: { onGiveUp: (reason: string) => void }) {
  const { t } = useT();
  useEffect(() => {
    const started = Date.now();
    let sawDown = false;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      if (stopped) return;
      let up = true;
      try {
        await apiGet("/status");
      } catch {
        up = false;
      }
      const elapsed = Date.now() - started;
      if (!up) sawDown = true;
      else if (sawDown) {
        window.location.reload();
        return;
      } else if (elapsed > NEVER_WENT_DOWN_MS) {
        onGiveUp(translate("restart.neverDown"));
        return;
      }
      if (elapsed > NEVER_CAME_BACK_MS) {
        onGiveUp(translate("restart.neverBack"));
        return;
      }
      timer = setTimeout(tick, 1000);
    };
    timer = setTimeout(tick, 1500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [onGiveUp]);

  return (
    <AlertDialog open>
      <AlertDialogContent onEscapeKeyDown={(e) => e.preventDefault()}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("restart.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("restart.description")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          <span>{t("restart.waiting")}</span>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
