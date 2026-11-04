// Password + 6-digit code. A real <form> so Enter submits and password managers recognise the fields.
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Field } from "@workspace/pds/components/ui/field";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@workspace/pds/components/ui/input-otp";
import { Stack } from "@workspace/pds/components/ui/layout";
import { errorText, postLogin } from "./loginApi";
import { useFieldSize } from "../lib/useFieldSize";
import { translate as t } from "../lib/i18n";

export default function LoginForm({ notice }: { notice: string | null }) {
  const fieldSize = useFieldSize();
  // OTP slots have no size prop: on a phone they get the height of a large Field (3.5rem) and slots that share the row, so the group is as wide as the password field
  const slotStyle = fieldSize === "lg" ? { height: "var(--dim-l)", flex: "1 1 0", minWidth: 0 } : undefined;
  const groupStyle = fieldSize === "lg" ? { width: "100%" } : undefined;
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!password || code.length !== 6) {
      setError(t("login.fillAll"));
      return;
    }
    setBusy(true);
    try {
      const r = await postLogin(password, code);
      window.location.replace(r.next || "/eden/home"); // the session cookie is already set; stay "busy" until the page changes
    } catch (err) {
      setError(errorText(err, "login"));
      setCode("");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="s">
      {notice && (
        <Alert>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      <Field size={fieldSize}
        label={t("login.password")}
        type="password"
        autoComplete="current-password"
        value={password}
        disabled={busy}
        state={error ? "error" : "default"}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Stack gap="ss" className="items-center">
        <span className="text-xs text-muted-foreground">{t("login.codeLabel")}</span>
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
        {busy ? t("login.busy") : t("login.submit")}
      </Button>
      </Stack>
    </form>
  );
}
