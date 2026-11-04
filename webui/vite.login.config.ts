// Second build of the same project: the login / enrollment app that eden_remote serves to remote devices.
// base "/eden/": eden_remote owns that prefix and serves only dist-login/assets/*, dist-login/logo.svg and
// the index; "/" belongs to the proxy behind it. Run through "pnpm build" (see package.json).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/eden/",
  plugins: [react()],
  build: { outDir: "dist-login", emptyOutDir: true, rollupOptions: { input: "login.html" } },
});
