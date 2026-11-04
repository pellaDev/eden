// Add service and Edit service: the same PDS Sheet from the right, with the same fields.
// The Fields follow the global fill/outline style set in Settings. A new service always starts off.
// In edit mode the form starts from `service` and is put back to it whenever the sheet closes.
import { useRef, useState } from "react";
import { Info } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Stack } from "@workspace/pds/components/ui/layout";
import { Field } from "@workspace/pds/components/ui/field";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@workspace/pds/components/ui/sheet";
import AvatarPicker from "./AvatarPicker";
import OnOff from "./OnOff";
import type { Service } from "./ServiceCard";
import { useFieldSize } from "../lib/useFieldSize";
import { useHost } from "../lib/host";
import { useWindows } from "../lib/platform";
import { useT } from "../lib/i18n";

export type ServiceForm = {
  name: string;
  port: number;
  note: string;
  avatar: string | null;
  avatarChanged: boolean; // false: leave the stored picture alone (edit mode)
  forward: boolean;
};

const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const FORWARD_MIN_PORT = 1024; // the forwarder runs as the normal user
const errorStyle = { color: "var(--color-destructive)" } as const;

export default function ServiceSheet({
  mode,
  open,
  onOpenChange,
  service,
  existingNames,
  onSubmit,
}: {
  mode: "add" | "edit";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  service?: Service; // edit mode: the service being edited
  existingNames: string[]; // names already taken, without the one being edited
  onSubmit: (form: ServiceForm) => Promise<string | null>; // resolves to an error message, or null on success
}) {
  const initial = {
    name: service?.name ?? "",
    port: service ? String(service.port) : "",
    note: service?.note ?? "",
    avatar: service?.avatar ?? null,
    forward: service?.forward ?? false,
  };
  const { t } = useT();
  const fieldSize = useFieldSize();
  const { hostName } = useHost();
  const windows = useWindows();
  const [name, setName] = useState(initial.name);
  const [port, setPort] = useState(initial.port);
  const [note, setNote] = useState(initial.note);
  const [avatar, setAvatar] = useState<string | null>(initial.avatar);
  const [avatarChanged, setAvatarChanged] = useState(false);
  const [forward, setForward] = useState(initial.forward);
  const [tried, setTried] = useState(false); // validation messages appear only after the first submit attempt
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const portNum = Number(port);
  const nameError = !NAME_RE.test(name)
    ? t("service.nameError")
    : existingNames.includes(name)
      ? t("service.nameTaken")
      : null;
  const portError =
    !Number.isInteger(portNum) || portNum < 1 || portNum > 65535
      ? t("service.portError")
      : forward && portNum < FORWARD_MIN_PORT
        ? t("service.portForwardError", { min: FORWARD_MIN_PORT })
        : null;
  const portChanged = mode === "edit" && service !== undefined && portNum !== service.port;

  const reset = () => {
    setName(initial.name);
    setPort(initial.port);
    setNote(initial.note);
    setAvatar(initial.avatar);
    setAvatarChanged(false);
    setForward(initial.forward);
    setTried(false);
    setServerError(null);
  };
  const change = (next: boolean) => {
    if (saving) return;
    if (!next) reset();
    onOpenChange(next);
  };

  const submit = async () => {
    setTried(true);
    setServerError(null);
    if (nameError || portError) return;
    setSaving(true);
    const err = await onSubmit({ name, port: portNum, note: note.trim(), avatar, avatarChanged, forward });
    setSaving(false);
    if (err) setServerError(err);
    else {
      if (mode === "add") reset();
      onOpenChange(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={change}>
      <SheetContent
        side="right"
        style={{ width: "min(100vw, 28rem)", maxWidth: "28rem", overflowY: "auto" }}
        // Start on the first field instead of the close button
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          nameRef.current?.focus();
        }}
      >
        <Stack gap="s">
          <SheetHeader>
            <SheetTitle>{mode === "add" ? t("services.add") : t("services.edit")}</SheetTitle>
            <SheetDescription>
              {mode === "add"
                ? t("service.sheetAddDescription", { host: hostName })
                : t("service.sheetEditDescription")}
            </SheetDescription>
          </SheetHeader>

          <AvatarPicker
            name={name}
            value={avatar}
            onChange={(a) => {
              setAvatar(a);
              setAvatarChanged(true);
            }}
          />

          <div>
            <Field size={fieldSize} ref={nameRef} label={t("common.name")} value={name} state={tried && nameError ? "error" : "default"} onChange={(e) => setName(e.target.value.toLowerCase())} />
            <p className="text-xs" style={tried && nameError ? errorStyle : { opacity: 0.7 }}>
              {tried && nameError ? nameError : t("service.nameHelp")}
            </p>
          </div>
          <div>
            <Field size={fieldSize}
              label={t("service.portLabel")}
              type="number"
              inputMode="numeric"
              min={1}
              max={65535}
              value={port}
              state={tried && portError ? "error" : "default"}
              onChange={(e) => setPort(e.target.value)}
            />
            <p className="text-xs" style={tried && portError ? errorStyle : { opacity: 0.7 }}>
              {tried && portError ? portError : t("service.portHelp", { host: hostName })}
            </p>
          </div>
          <div>
            <Field size={fieldSize} label={t("service.noteLabel")} value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} />
            <p className="text-xs" style={{ opacity: 0.7 }}>
              {t("service.noteHelp")}
            </p>
          </div>

          <div className="flex items-center justify-between gap-4">
            <div style={{ minWidth: 0 }}>
              <div className="text-sm">{t("service.forwardTitle")}</div>
              <div className="text-xs text-muted-foreground">
                {t("service.sheetForwardHint")}
              </div>
            </div>
            <OnOff label={t("service.forwardTitle")} value={forward} onChange={setForward} />
          </div>

          {portChanged && (
            <Alert>
              <Info size={16} />
              <AlertDescription>{t("service.portChangeAlert")}</AlertDescription>
            </Alert>
          )}
          <Alert>
            <Info size={16} />
            <AlertDescription>
              {t(windows ? "service.allowedPortsAlert.win" : "service.allowedPortsAlert")}
            </AlertDescription>
          </Alert>
          {serverError && (
            <Alert variant="destructive">
              <AlertDescription style={{ whiteSpace: "pre-wrap" }}>{serverError}</AlertDescription>
            </Alert>
          )}

          <SheetFooter>
            <Button variant="link" size="small" disabled={saving} onClick={() => change(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="default" size="small" disabled={saving} onClick={submit}>
              {saving ? t("common.saving") : mode === "add" ? t("services.add") : t("common.save")}
            </Button>
          </SheetFooter>
        </Stack>
      </SheetContent>
    </Sheet>
  );
}
