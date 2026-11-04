// Picture chooser shared by the service and device sheets: preview, choose / remove buttons, and the
// client-side crop + resize (see lib/image.ts). The parent only sees the resulting data URL, or null.
import { useRef, useState, type ChangeEvent } from "react";
import { ImagePlus } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { AVATAR_TYPES, fileToAvatar } from "../lib/image";
import { useT } from "../lib/i18n";
import NameAvatar from "./NameAvatar";

export default function AvatarPicker({
  name,
  value,
  onChange,
}: {
  name: string; // initials shown while there is no picture
  value: string | null;
  onChange: (avatar: string | null) => void;
}) {
  const { t } = useT();
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const pick = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again
    if (!file) return;
    try {
      onChange(await fileToAvatar(file));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <Row gap="s">
        <NameAvatar name={name || "?"} src={value} size={72} outlined />
        <Stack gap="ss">
          <Row gap="ss">
            <Button variant="default" size="small" onClick={() => fileRef.current?.click()}>
              <ImagePlus /> {t("avatar.choose")}
            </Button>
            {value && (
              <Button variant="link" size="small" onClick={() => onChange(null)}>
                {t("common.remove")}
              </Button>
            )}
          </Row>
          <span className="text-xs text-muted-foreground">{t("avatar.hint")}</span>
        </Stack>
        <input ref={fileRef} type="file" accept={AVATAR_TYPES} onChange={pick} style={{ display: "none" }} />
      </Row>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}
