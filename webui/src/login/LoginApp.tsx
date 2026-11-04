// The page remote devices see before logging in: the content sits directly on the full-screen page, no Card, in a
// centered column that stays fluid down to a phone screen. Which screen it shows (login, first setup, "not
// available") comes from eden_remote, not from the URL; light/dark and the fill/outline field style come from what
// is set in Eden local's Settings on the Eden computer.
import { useCallback, useEffect, useState } from "react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Stack } from "@workspace/pds/components/ui/layout";
import { Spinner } from "@workspace/pds/components/ui/spinner";
import { setPdsConfig } from "@workspace/pds/config";
import Logo from "../components/Logo";
import EnrollForm from "./EnrollForm";
import HomeDashboard from "./HomeDashboard";
import LoginForm from "./LoginForm";
import { getState, type Appearance, type AppState } from "./loginApi";
import { setLanguage, translate as t } from "../lib/i18n";

function applyAppearance(a: Appearance) {
  // No saved choice yet (Settings was never opened): follow this device.
  const dark = a.theme ? a.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
  // Since PDS 1.10 setPdsConfig also writes data-pds-fieldstyle on <html>, which cards, borders and separators read.
  setPdsConfig({ fieldStyle: a.field_style ?? "fill" });
}

const subtitle = (mode: AppState["mode"]) =>
  mode === "login" ? t("login.subtitleLogin") : mode === "home" ? "\u00a0" : mode === "enroll" ? t("login.subtitleEnroll") : t("login.subtitleClosed");

export default function LoginApp() {
  const [state, setState] = useState<AppState | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getState();
      applyAppearance(s.appearance);
      setLanguage(s.language ?? "en"); // before setState: the screens below read it while rendering
      setState(s);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    // The page is a PDS "alternative" surface: its background is --pds-surface-bg (= --color-secondary, the same grey
    // the body has in login.html) and PDS paints Fields and OTP slots for exactly that surface (--color-background in
    // fill, a border in outline), so they stand out from the page in light and dark. With the "base" surface they
    // would be --color-secondary on --color-background: the right pair only for a page that is --color-background.
    <div
      data-pds-surface="alternative"
      style={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "max(1.5rem, env(safe-area-inset-top)) 1.5rem max(1.5rem, env(safe-area-inset-bottom))",
        boxSizing: "border-box",
        background: "var(--pds-surface-bg)",
        color: "var(--pds-surface-fg)",
      }}
    >
      <div style={{ width: "100%", maxWidth: state?.mode === "home" ? "40rem" : "24rem" }}>
        <Stack gap="m">
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", textAlign: "center" }}>
            <Logo size={72} />
            <h1 className="text-xl font-semibold">Eden</h1>
            <p className="text-sm text-muted-foreground">{state ? subtitle(state.mode) : "\u00a0"}</p>
          </div>
          <Stack gap="s">
            {!state && !failed && (
              <div style={{ display: "flex", justifyContent: "center", padding: "1rem" }}>
                <Spinner />
              </div>
            )}
            {failed && (
              <>
                <Alert variant="destructive">
                  <AlertDescription>{t("login.unreachable")}</AlertDescription>
                </Alert>
                <Button variant="default" size="large" onClick={() => void refresh()}>
                  {t("login.retry")}
                </Button>
              </>
            )}
            {state?.mode === "login" && <LoginForm notice={notice} />}
            {state?.mode === "home" && <HomeDashboard onLoggedOut={() => void refresh()} />}
            {state?.mode === "enroll" && (
              <EnrollForm
                remaining={state.remaining}
                onDone={() => {
                  setNotice(t("login.enrolled"));
                  void refresh();
                }}
                onExpired={() => void refresh()}
              />
            )}
            {state?.mode === "closed" && (
              <>
                <Alert>
                  <AlertDescription>
                    {t("login.closedMessage")}
                  </AlertDescription>
                </Alert>
                <Button variant="default" size="large" onClick={() => void refresh()}>
                  {t("login.reload")}
                </Button>
              </>
            )}
          </Stack>
        </Stack>
      </div>
    </div>
  );
}
