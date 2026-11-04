import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "./layout/Sidebar";
import PageLoading from "./components/PageLoading";
import Vpn from "./pages/Vpn";
import Devices from "./pages/Devices";
import Services from "./pages/Services";
import Audit from "./pages/Audit";
import Notifications from "./pages/Notifications";
import SettingsPage from "./pages/SettingsPage";
import { HostProvider } from "./lib/host";
import { I18nProvider } from "./lib/i18n";
import { LiveProvider } from "./lib/live";

// Loaded on demand: the Home monitor brings the chart library, which no other page needs.
const Home = lazy(() => import("./pages/Home"));

export default function App() {
  return (
    <I18nProvider>
    <HostProvider>
    <LiveProvider>
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Suspense fallback={<PageLoading title="Monitor Meshnet" error={null} />}><Home /></Suspense>} />
          <Route path="/vpn" element={<Vpn />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/services" element={<Services />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
    </LiveProvider>
    </HostProvider>
    </I18nProvider>
  );
}
