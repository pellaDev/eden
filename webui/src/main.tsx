import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./lib/theme";
import "@workspace/pds/styles.css";
import "./eden.css";

// Apply the saved theme before anything renders, so every page starts in the right theme.
initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
