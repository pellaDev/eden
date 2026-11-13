// "Edit device": name and picture. A device is identified by its public key, which is shown but cannot
// change: renaming is cosmetic and keeps every permission. The form is put back to the device when the sheet closes.
import { useRef, useState } from "react";
import { Info } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Radio } from "@workspace/pds/components/ui/radio";
import { Stack } from "@workspace/pds/components/ui/layout";
import { Field } from "@workspace/pds/components/ui/field";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@workspace/pds/components/ui/sheet";
import AvatarPicker from "./AvatarPicker";
import { useFieldSize } from "../lib/useFieldSize";
import { useT } from "../lib/i18n";

export type DeviceInfo = { name: string; public_key: string; avatar?: string | null; external?: boolean; meshnet?: string | null };
export type DeviceForm = { name: string; avatar: string | null; avatarChanged: boolean; meshnet: string }; // meshnet: "", mine, theirs, both

const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const errorStyle = { color: "var(--color-destructive)" } as const;

export default function EditDeviceSheet({
  open,
  onOpenChange,
  device,
  existingNames,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  device: DeviceInfo;
  existingNames: string[]; // other devices' names (not this one's)
  onSubmit: (form: DeviceForm) => Promise<string | null>; // resolves to an error message, or null on success
}) {
  const fieldSize = useFieldSize();
  const { t } = useT();
  const [name, setName] = useState(device.name);
  const [avatar, setAvatar] = useState<string | null>(device.avatar ?? null);
  const [avatarChanged, setAvatarChanged] = useState(false);
  const [meshnet, setMeshnet] = useState(device.meshnet ?? "");
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const nameError = !NAME_RE.test(name)
    ? t("editDevice.nameInvalid")
    : existingNames.includes(name)
      ? t("editDevice.nameTaken")
      : null;

  const reset = () => {
    setName(device.name);
    setAvatar(device.avatar ?? null);
    setAvatarChanged(false);
    setMeshnet(device.meshnet ?? "");
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
    if (nameError) return;
    setSaving(true);
    const err = await onSubmit({ name, avatar, avatarChanged, meshnet });
    setSaving(false);
    if (err) setServerError(err);
    else onOpenChange(false);
  };

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
            <SheetTitle>{t("editDevice.title")}</SheetTitle>
            <SheetDescription>{t("editDevice.description")}</SheetDescription>
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
              {tried && nameError ? nameError : t("editDevice.nameHint")}
            </p>
          </div>

          {device.external && (
            <div>
              <div className="text-sm">{t("editDevice.meshnetTitle")}</div>
              <Stack gap="ss">
              {(
                [
                  ["", "editDevice.meshnetNone"],
                  ["mine", "editDevice.meshnetMine"],
                  ["theirs", "editDevice.meshnetTheirs"],
                  ["both", "editDevice.meshnetBoth"],
                ] as const
              ).map(([value, label]) => (
                <Radio key={value} name="meshnet" label={t(label)} checked={meshnet === value} onChange={() => setMeshnet(value)} />
              ))}
              </Stack>
              <p className="text-xs" style={{ opacity: 0.7 }}>
                {t("editDevice.meshnetHint")}
              </p>
            </div>
          )}

          <div>
            <div className="text-xs text-muted-foreground">{t("editDevice.publicKey")}</div>
            <div className="text-xs" style={{ wordBreak: "break-all", fontFamily: "monospace" }}>
              {device.public_key}
            </div>
          </div>

          {device.public_key.startsWith("addr:") && (
            // A Windows device is identified by this address alone. If Nord reassigns it, the permissions follow the
            // old number and the device stops working: the warning belongs here, next to the identity.
            <Alert>
              <Info size={16} />
              <AlertDescription>{t("editDevice.addressIdentity")}</AlertDescription>
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
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </SheetFooter>
        </Stack>
      </SheetContent>
    </Sheet>
  );
}
