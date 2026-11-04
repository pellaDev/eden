import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Version of the installed Design System, shown in Settings. Read at build time from the package itself; "?" if the
// package.json cannot be read (the build must not fail for a label).
function pdsVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(new URL("./node_modules/@workspace/pds/package.json", import.meta.url), "utf8"));
    return typeof pkg.version === "string" ? pkg.version : "?";
  } catch {
    return "?";
  }
}

// Built as static files, served by the Eden local FastAPI backend on loopback.
// No dev-server proxy assumptions here: in dev, point VITE_API_BASE at the
// backend directly (see src/lib/api.ts); in prod it's same-origin.
export default defineConfig({
  plugins: [react()],
  define: { __PDS_VERSION__: JSON.stringify(pdsVersion()) },
  build: { outDir: "dist", emptyOutDir: true },
});
