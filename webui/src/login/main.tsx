// Entry of the login app (second build, see vite.login.config.ts). Until the server says how Eden looks on
// the Eden computer, follow this device's own light/dark preference.
import React from "react";
import ReactDOM from "react-dom/client";
import "@workspace/pds/styles.css";
import LoginApp from "./LoginApp";

document.documentElement.classList.toggle("dark", window.matchMedia("(prefers-color-scheme: dark)").matches);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LoginApp />
  </React.StrictMode>
);
