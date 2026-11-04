// The Eden logo: webui/public/logo.svg, served at /logo.svg by Eden local and at /eden/logo.svg by Eden remote's
// login page (BASE_URL is "/" in the main build and "/eden/" in the login build). The same file is the favicon.
// Until that file exists the letter placeholder is shown instead of a broken image.
import { useState } from "react";

// size: pixels (number) or any CSS length (string), e.g. "min(80vw, 28rem)" for the big one on the home page.
export default function Logo({ size = 32 }: { size?: number | string }) {
  const [missing, setMissing] = useState(false);
  if (missing) {
    return (
      <div
        aria-label="Eden logo (placeholder)"
        className="flex shrink-0 items-center justify-center rounded-md border border-dashed text-xs font-semibold text-muted-foreground"
        style={{ width: size, height: size }}
      >
        E
      </div>
    );
  }
  return <img src={`${import.meta.env.BASE_URL}logo.svg`} alt="Eden" onError={() => setMissing(true)} style={{ display: "block", flexShrink: 0, width: size, height: size }} />;
}
