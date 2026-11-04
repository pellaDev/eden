// First setup / re-enrollment, shown only while the window opened from Eden local's Settings is open: countdown,
// the QR code for the authenticator app, a new password (typed twice, a typo here would lock the owner out) and
// the first code to prove the app is set up.
import { useEffect, useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Field } from "@workspace/pds/components/ui/field";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@workspace/pds/components/ui/input-otp";
import { Progress } from "@workspace/pds/components/ui/progress";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { ApiError, errorText, postEnroll } from "./loginApi";
import { useFieldSize } from "../lib/useFieldSize";
import { translate as t } from "../lib/i18n";

const WINDOW_SECONDS = 10 * 60; // the window Eden local opens; only used to size the progress bar
const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function EnrollForm({ remaining, onDone, onExpired }: { remaining: number; onDone: () => void; onExpired: () => void }) {
  const fieldSize = useFieldSize();
  // OTP slots have no size prop: on a phone they get the height of a large Field (3.5rem) and slots that share the row, so the group is as wide as the password field
  const slotStyle = fieldSize === "lg" ? { height: "var(--dim-l)", flex: "1 1 0", minWidth: 0 } : undefined;
  const groupStyle = fieldSize === "lg" ? { width: "100%" } : undefined;
  const [left, setLeft] = useState(remaining);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (left <= 0) onExpired();
  }, [left, onExpired]);

  const mismatch = confirm !== "" && confirm !== password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!password) return setError(t("login.choosePassword"));
    if (password !== confirm) return setError(t("login.mismatch"));
    if (code.length !== 6) return setError(t("login.enterCode"));
    setBusy(true);
    try {
      await postEnroll(password, code);
      onDone();
    } catch (err) {
      if (err instanceof ApiError && (err.status === 403 || err.status === 409)) return onExpired(); // window closed meanwhile
      setError(errorText(err, "enroll"));
      setCode("");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="s">
      <Stack gap="ss">
        <Row gap="ss" className="text-sm justify-between">
          <span>{t("settings.timeLeft")}</span>
          <span style={{ fontWeight: 600 }}>{clock(left)}</span>
        </Row>
        <Progress value={Math.min(100, (left / WINDOW_SECONDS) * 100)} aria-label={t("settings.timeLeft")} />
        {left < 60 && <span className="text-xs">{t("settings.hurry")}</span>}
      </Stack>
      <p className="text-sm text-muted-foreground">
        {t("login.enrollHint")}
      </p>
      <img
        src="/eden/enroll.png"
        alt={t("login.qrAlt")}
        width={200}
        height={200}
        style={{ alignSelf: "center", background: "#fff", padding: "0.5rem", borderRadius: "0.5rem", imageRendering: "pixelated" }}
      />
      <Field size={fieldSize} label={t("login.newPassword")} type="password" autoComplete="new-password" value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} />
      <Field size={fieldSize}
        label={t("login.confirmPassword")}
        type="password"
        autoComplete="new-password"
        value={confirm}
        disabled={busy}
        state={mismatch ? "error" : "default"}
        onChange={(e) => setConfirm(e.target.value)}
      />
      <Stack gap="ss" className="items-center">
        <span className="text-xs text-muted-foreground">{t("login.firstCode")}</span>
        <InputOTP containerClassName={fieldSize === "lg" ? "w-full" : undefined} maxLength={6} value={code} onChange={setCode} pattern="^\d+$" inputMode="numeric" autoComplete="one-time-code" disabled={busy}>
          <InputOTPGroup style={groupStyle}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <InputOTPSlot key={i} index={i} style={slotStyle} />
            ))}
          </InputOTPGroup>
        </InputOTP>
      </Stack>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button type="submit" variant="default" size="large" disabled={busy} style={{ width: "100%" }}>
        {busy ? t("login.saving") : t("login.confirm")}
      </Button>
      </Stack>
    </form>
  );
}
