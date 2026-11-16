// Banner shown on the Home page when a newer Eden or NordVPN is available. It fetches /api/update/status
// once per mount and can be dismissed for this browser session; dismissal is remembered per version pair,
// so the banner comes back if an even newer release appears later.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { X } from "lucide-react";
import { useT } from "../lib/i18n";
import { updateStatus, type UpdateStatus } from "../lib/update";

const DISMISS_KEY = "eden.update-notice.dismissed";

export default function UpdateNotice() {
  const { t } = useT();
  const navigate = useNavigate();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [dismissed, setDismissed] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem(DISMISS_KEY) ?? "[]"); } catch { return []; }
  });

  useEffect(() => {
    let live = true;
    updateStatus().then((s) => { if (live) setStatus(s); }).catch(() => undefined);
    return () => { live = false; };
  }, []);

  if (!status) return null;
  const eden = status.eden.available && status.eden.installed && status.eden.latest;
  const nord = status.nordvpn.available && status.nordvpn.installed && status.nordvpn.latest;
  if (!eden && !nord) return null;
  // One dismissal per pair of latest versions: update one side and the banner can reappear.
  const key = [status.eden.latest ?? "-", status.nordvpn.latest ?? "-"].join("/");
  if (dismissed.includes(key)) return null;

  const dismiss = () => {
    const next = [...new Set([...dismissed, key])].slice(-5);
    sessionStorage.setItem(DISMISS_KEY, JSON.stringify(next));
    setDismissed(next);
  };

  return (
    <Alert style={{ borderColor: "#d97706" }}>
      <AlertDescription>
        <strong>{t("update.noticeTitle")}</strong>
        {eden && status.eden.installed && status.eden.latest && (
          <div>{t("update.noticeEden", { installed: status.eden.installed, latest: status.eden.latest })}</div>
        )}
        {nord && status.nordvpn.installed && status.nordvpn.latest && (
          <div>{t("update.noticeNordvpn", { installed: status.nordvpn.installed, latest: status.nordvpn.latest })}</div>
        )}
        <button type="button" onClick={() => navigate("/settings")} className="text-sm underline cursor-pointer">
          {t("update.noticeSettings")}
        </button>
      </AlertDescription>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("update.noticeTitle")}
        style={{ position: "absolute", right: "0.5rem", top: "0.5rem", color: "inherit", cursor: "pointer" }}
      >
        <X size={14} />
      </button>
    </Alert>
  );
}
