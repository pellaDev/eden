// Add remote service and Edit remote service: a PDS Sheet from the right. The device is picked from the live Meshnet
// peers (kept by public key); the rest is a name, the port the device listens on and an optional note.
import { useRef, useState } from "react";
import { Info } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Stack } from "@workspace/pds/components/ui/layout";
import { Field } from "@workspace/pds/components/ui/field";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@workspace/pds/components/ui/sheet";
import type { RemoteService } from "./RemoteServiceCard";
import { useFieldSize } from "../lib/useFieldSize";
import { useT } from "../lib/i18n";

export type RemotePeer = { public_key: string; label: string; ip: string; offered: boolean; external: boolean };
export type RemoteServiceForm = { name: string; public_key: string; port: number; note: string };

const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const errorStyle = { color: "var(--color-destructive)" } as const;

export default function RemoteServiceSheet({
  mode,
  open,
  onOpenChange,
  service,
  peers,
  peersOk,
  existingNames,
  onSubmit,
}: {
  mode: "add" | "edit";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  service?: RemoteService;
  peers: RemotePeer[];
  peersOk: boolean; // false while the VPN is off: the peer list is not readable
  existingNames: string[]; // names already taken, without the one being edited
  onSubmit: (form: RemoteServiceForm) => Promise<string | null>; // resolves to an error message, or null on success
}) {
  const initial = { name: service?.name ?? "", key: service?.public_key ?? "", port: service ? String(service.port) : "", note: service?.note ?? "" };
  const { t } = useT();
  const fieldSize = useFieldSize();
  const [name, setName] = useState(initial.name);
  const [key, setKey] = useState(initial.key);
  const [port, setPort] = useState(initial.port);
  const [note, setNote] = useState(initial.note);
  const [tried, setTried] = useState(false); // validation messages appear only after the first submit attempt
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const portNum = Number(port);
  const nameError = !NAME_RE.test(name) ? t("service.nameError") : existingNames.includes(name) ? t("service.nameTaken") : null;
  const portError = !Number.isInteger(portNum) || portNum < 1 || portNum > 65535 ? t("service.portError") : null;
  const keyError = key ? null : t("services.remoteDeviceError");

  const reset = () => {
    setName(initial.name);
    setKey(initial.key);
    setPort(initial.port);
    setNote(initial.note);
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
    if (nameError || portError || keyError) return;
    setSaving(true);
    const err = await onSubmit({ name, public_key: key, port: portNum, note: note.trim() });
    setSaving(false);
    if (err) setServerError(err);
    else {
      if (mode === "add") reset();
      onOpenChange(false);
    }
  };

  // The stored device may not be in the live list (VPN off, or it left the Meshnet): keep it selectable so an edit of
  // the name or the port does not silently change the device.
  const options = peers.some((p) => p.public_key === key) || !key ? peers : [{ public_key: key, label: service?.device ?? key, ip: "", offered: false, external: false }, ...peers];

  return (
    <Sheet open={open} onOpenChange={change}>
      <SheetContent
        side="right"
        style={{ width: "min(100vw, 28rem)", maxWidth: "28rem", overflowY: "auto" }}
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          nameRef.current?.focus();
        }}
      >
        <Stack gap="s">
          <SheetHeader>
            <SheetTitle>{mode === "add" ? t("services.remoteAdd") : t("services.remoteEdit")}</SheetTitle>
            <SheetDescription>{t("services.remoteSheetDescription")}</SheetDescription>
          </SheetHeader>

          <div>
            <Field size={fieldSize} ref={nameRef} label={t("common.name")} value={name} state={tried && nameError ? "error" : "default"} onChange={(e) => setName(e.target.value.toLowerCase())} />
            <p className="text-xs" style={tried && nameError ? errorStyle : { opacity: 0.7 }}>
              {tried && nameError ? nameError : t("service.nameHelp")}
            </p>
          </div>

          <div>
            <label className="text-sm" htmlFor="remote-device">
              {t("services.remoteDevice")}
            </label>
            <select
              id="remote-device"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem 0.75rem",
                marginTop: "0.25rem",
                borderRadius: "var(--radius-m, 0.5rem)",
                border: `1px solid ${tried && keyError ? "var(--color-destructive)" : "var(--color-border)"}`,
                background: "var(--color-card)",
                color: "inherit",
                font: "inherit",
              }}
            >
              <option value="">{t("services.remoteDevicePick")}</option>
              {options.map((p) => (
                <option key={p.public_key} value={p.public_key}>
                  {p.offered ? t("services.remoteDeviceOffers", { label: p.label }) : p.label}
                  {p.ip ? ` · ${p.ip}` : ""}
                </option>
              ))}
            </select>
            <p className="text-xs" style={tried && keyError ? errorStyle : { opacity: 0.7 }}>
              {tried && keyError ? keyError : t("services.remoteDeviceHelp")}
            </p>
          </div>

          <div>
            <Field size={fieldSize} label={t("service.portLabel")} type="number" inputMode="numeric" min={1} max={65535} value={port} state={tried && portError ? "error" : "default"} onChange={(e) => setPort(e.target.value)} />
            <p className="text-xs" style={tried && portError ? errorStyle : { opacity: 0.7 }}>
              {tried && portError ? portError : t("services.remotePortHelp")}
            </p>
          </div>
          <div>
            <Field size={fieldSize} label={t("service.noteLabel")} value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} />
            <p className="text-xs" style={{ opacity: 0.7 }}>
              {t("service.noteHelp")}
            </p>
          </div>

          {!peersOk && (
            <Alert>
              <Info size={16} />
              <AlertDescription>{t("services.remoteDeviceVpnOff")}</AlertDescription>
            </Alert>
          )}
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
              {saving ? t("common.saving") : mode === "add" ? t("services.remoteAdd") : t("common.save")}
            </Button>
          </SheetFooter>
        </Stack>
      </SheetContent>
    </Sheet>
  );
}
