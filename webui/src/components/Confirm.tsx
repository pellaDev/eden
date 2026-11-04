// Confirmation dialog replacing window.confirm. Controlled (open state kept here) because the PDS Button
// does not forward refs, so AlertDialogTrigger asChild cannot attach to it; the caller renders the trigger.
import { useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@workspace/pds/components/ui/alert-dialog";
import { buttonVariants } from "@workspace/pds/components/ui/button";
import { useT } from "../lib/i18n";

export default function Confirm({
  trigger,
  title,
  description,
  actionLabel,
  destructive = false,
  onConfirm,
}: {
  trigger: (open: () => void) => ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  destructive?: boolean; // style the confirm action like the destructive Button that usually opens it
  onConfirm: () => void;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      {trigger(() => setOpen(true))}
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            <AlertDialogDescription>{description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction className={destructive ? buttonVariants({ variant: "destructive" }) : undefined} onClick={onConfirm}>{actionLabel ?? t("common.continue")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
