// App shell built on the PDS Template: header on top, page canvas, and navigation in one of two forms that PDS picks
// itself at 48rem (useIsMobile): a resizable sidebar on the left (desktop) or an off-canvas drawer opened from a button
// in the header (phone), on the right, opening the PDS panel from the right (side="right"). The two forms are never mounted together: on a phone the "sidebar" prop is left undefined,
// because TemplateBody renders whatever it gets inline above the page and the desktop sidebar fills the whole height.
import { NavLink, useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarProvider,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarGroup,
} from "@workspace/pds/components/ui/sidebar";
import {
  Template,
  TemplateHeader,
  TemplateSubHeader,
  TemplateBody,
  TemplateCanvas,
  TemplateFooter,
} from "@workspace/pds/components/ui/template";
import { Badge } from "@workspace/pds/components/ui/badge";
import { ScrollArea } from "@workspace/pds/components/ui/scroll-area";
import { Toaster } from "@workspace/pds/components/ui/toaster";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@workspace/pds/components/ui/breadcrumb";
import {
  MobileNavigationMenu,
  MobileNavigationMenuClose,
  MobileNavigationMenuContent,
  MobileNavigationMenuDescription,
  MobileNavigationMenuHeader,
  MobileNavigationMenuItem,
  MobileNavigationMenuPanel,
  MobileNavigationMenuSeparator,
  MobileNavigationMenuTitle,
  MobileNavigationMenuTrigger,
} from "@workspace/pds/components/ui/mobile-navigation-menu";
import { Row } from "@workspace/pds/components/ui/layout";
import { useIsMobile } from "@workspace/pds/hooks/use-mobile";
import { Bell, Home, ShieldCheck, MonitorSmartphone, Waypoints, ScrollText, Settings } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import Logo from "../components/Logo";
import { usePoll } from "../lib/usePoll";
import { useLive } from "../lib/live";
import { useSessionAvailable, useVersion } from "../lib/platform";
import { useT, type TextKey } from "../lib/i18n";
import OnOff from "../components/OnOff";


const NAV: { to: string; label: TextKey; icon: typeof Home; session?: boolean }[] = [
  { to: "/", label: "nav.home", icon: Home },
  { to: "/vpn", label: "nav.vpn", icon: ShieldCheck },
  { to: "/devices", label: "nav.devices", icon: MonitorSmartphone },
  { to: "/services", label: "nav.services", icon: Waypoints },
  { to: "/notifications", label: "nav.notifications", icon: Bell },
  { to: "/audit", label: "nav.audit", icon: ScrollText },
];

function EdenSidebar() {
  const { pathname } = useLocation();
  const sessionAvailable = useSessionAvailable();
  const nav = NAV.filter((n) => !n.session || sessionAvailable);
  const { t } = useT();
  // Inline width: the PDS Sidebar has a fixed token width, which must not fight the resizable panel.
  return (
    <Sidebar collapsible="none" style={{ width: "100%" }}>
      <SidebarContent style={{ overflow: "hidden" }}>
        <ScrollArea type="auto" className="eden-scroll" style={{ flex: "1 1 0", minHeight: 0 }}>
        <SidebarGroup>
          <SidebarMenu>
            {nav.map(({ to, label, icon: Icon }) => (
              <SidebarMenuItem key={to}>
                <SidebarMenuButton asChild isActive={pathname === to}>
                  <NavLink to={to}>
                    <Icon className="size-4" />
                    <span>{t(label)}</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
        </ScrollArea>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={pathname === "/settings"}>
              <NavLink to="/settings">
                <Settings className="size-4" />
                <span>{t("nav.settings")}</span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

// The phone form of the navigation: a drawer with the same entries as the sidebar, Settings last after a separator.
// Controlled, so a tap on an entry (a route change) closes it again.
function EdenMobileNav() {
  const { pathname } = useLocation();
  const sessionAvailable = useSessionAvailable();
  const nav = NAV.filter((n) => !n.session || sessionAvailable);
  const { t } = useT();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  const entry = (to: string, label: string, Icon: typeof Settings) => (
    <MobileNavigationMenuItem asChild isActive={pathname === to} key={to}>
      <NavLink to={to}>
        <Icon />
        <span>{label}</span>
      </NavLink>
    </MobileNavigationMenuItem>
  );
  return (
    <MobileNavigationMenu open={open} onOpenChange={setOpen}>
      <MobileNavigationMenuTrigger aria-label={t("nav.openMenu")} style={{ marginLeft: "auto" }} />
      <MobileNavigationMenuPanel side="right">
        <MobileNavigationMenuDescription className="sr-only">{t("nav.mainNavigation")}</MobileNavigationMenuDescription>
        <MobileNavigationMenuHeader>
          <MobileNavigationMenuTitle>Eden</MobileNavigationMenuTitle>
          <MobileNavigationMenuClose aria-label={t("nav.closeMenu")} />
        </MobileNavigationMenuHeader>
        <MobileNavigationMenuContent>
          {nav.map((n) => entry(n.to, t(n.label), n.icon))}
          <MobileNavigationMenuSeparator />
          {entry("/settings", t("nav.settings"), Settings)}
        </MobileNavigationMenuContent>
      </MobileNavigationMenuPanel>
    </MobileNavigationMenu>
  );
}

// Pages whose content is a set of cards laid out directly by the PDS "grid" canvas. Everything else sits in a
// centered column of fixed width. The columns are fluid (cards 18-24rem wide) and the grid is capped at
// GRID_MAX_COLUMNS and centered: on an ultrawide screen the page header (title left, action right) stays
// right above the cards instead of at the far edges of the monitor.
const GRID_PAGES = ["/", "/services"];
const GRID_MAX_COLUMNS = 4;

// Label key of the current page for the subheader (settings is not in NAV: it is pinned in the footer).
const pageLabelKey = (pathname: string): TextKey | null =>
  pathname === "/settings" ? "nav.settings" : NAV.find((n) => n.to === pathname)?.label ?? null;


// Compact VPN group state for the footer, polled like the pages (same /vpn endpoint as Vpn.tsx).
function FooterStatus() {
  const { t } = useT();
  const [vpn, setVpn] = useState<{ daemon: boolean; iface: boolean; remote: boolean } | null>(null);
  const load = useCallback(() => apiGet<typeof vpn>("/vpn").then(setVpn).catch(() => setVpn(null)), []);
  usePoll(load, 5000);
  const up = vpn ? [vpn.daemon, vpn.iface, vpn.remote].filter(Boolean).length : 0;
  const text = !vpn ? t("footer.vpnUnreachable") : up === 3 ? t("footer.vpnActive") : up === 0 ? t("footer.vpnStopped") : t("footer.vpnPartial");
  const vpnVariant = !vpn ? "error" : up === 3 ? "ready" : up === 0 ? "disabled" : "alert";
  return (
    <Row gap="ss" className="text-xs text-muted-foreground">
      <Badge variant={vpnVariant} aria-hidden="true" />
      <span>{text}</span>
    </Row>
  );
}

// Right end of the subheader, on every page: turns the Meshnet traffic scan on or off (it also decides whether the chart
// history keeps growing). Disabled until the first answer from the backend, so it never shows a guessed state.
function LiveTrafficSwitch() {
  const { info, busy, setLive } = useLive();
  const { t } = useT();
  return <OnOff label={t("live.switch")} text={t("live.switch")} value={info?.live ?? false} disabled={!info || busy} onChange={(v) => void setLive(v)} />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const grid = GRID_PAGES.includes(pathname);
  const isMobile = useIsMobile();
  const { t } = useT();
  const labelKey = pageLabelKey(pathname);
  const version = useVersion();
  return (
    <Template>
      <TemplateHeader>
        <Logo />
        <div className="flex flex-col leading-tight">
          <span className="font-semibold">Eden</span>
          <span className="text-xs text-muted-foreground">{version && `v${version}`}</span>
        </div>
        {isMobile && <EdenMobileNav />}
      </TemplateHeader>

      <TemplateBody
        defaultSidebarSize={12}
        minSidebarSize={9}
        subHeader={
          <TemplateSubHeader>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", width: "100%" }}>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <NavLink to="/">Eden</NavLink>
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{labelKey ? t(labelKey) : ""}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
            <LiveTrafficSwitch />
            </div>
          </TemplateSubHeader>
        }
        sidebar={
          isMobile ? undefined : (
            // SidebarProvider only supplies context here; reset its min-h-svh so it fits the panel.
            <SidebarProvider style={{ minHeight: 0, height: "100%" }}>
              <EdenSidebar />
            </SidebarProvider>
          )
        }
      >
        {/* The PDS ScrollArea provides the scrollbar; the canvas grows with its content and keeps the PDS "center"
            layout, with the wrapper giving pages one consistent width */}
        <ScrollArea
          type="auto"
          className="eden-scroll h-full"
          data-pds-surface="alternative"
          style={{ backgroundColor: "var(--pds-surface-bg)" }}
        >
          <TemplateCanvas
            layout={grid ? "grid" : "center"}
            style={{
              height: "auto",
              minHeight: "100%",
              overflow: "visible",
              flex: "1 0 auto",
              ...(grid
                ? {
                    gridTemplateColumns: "repeat(auto-fill, minmax(18rem, 24rem))",
                    justifyContent: "center",
                    // N columns + the gaps between them + the canvas padding on both sides (both are PDS canvas variables)
                    maxWidth: `calc(${GRID_MAX_COLUMNS} * 24rem + ${GRID_MAX_COLUMNS - 1} * var(--canvas-gap) + 2 * var(--canvas-padding))`,
                    marginInline: "auto",
                  }
                : {}),
            }}
          >
            {grid ? children : <div style={{ width: "100%", maxWidth: "40rem" }}>{children}</div>}
          </TemplateCanvas>
        </ScrollArea>
      </TemplateBody>

      <TemplateFooter>
        <FooterStatus />
        {!isMobile && <span className="text-xs text-muted-foreground">{t("footer.edenLocal")}</span>}
      </TemplateFooter>

      <Toaster />
    </Template>
  );
}
