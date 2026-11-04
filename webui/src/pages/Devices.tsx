// Devices allowed through Meshnet. Identified by public key (never by name/IP);
// new ones are picked from the live Meshnet peer list and start disabled and untrusted.
// "Accesso remoto" gates the browser-access port and the peer's Meshnet incoming
// permission (for an untrusted device it is only the incoming permission: "Dispositivo attivo");
// per-service grants live in the Servizi page. "Dispositivo UNTRUSTED": no remote login ever, only granted services;
// switching it on removes the device's grants; a device of another Nord account (external) cannot be made trusted.
import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@workspace/pds/components/ui/button";
import { Card } from "@workspace/pds/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader } from "@workspace/pds/components/ui/empty";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemSeparator,
  ItemTitle,
} from "@workspace/pds/components/ui/item";
import { Tag } from "@workspace/pds/components/ui/tag";
import { toast } from "@workspace/pds/hooks/use-toast";
import { apiDelete, apiGet, apiPost } from "../lib/api";
import AddDeviceSheet, { type Peer } from "../components/AddDeviceSheet";
import Confirm from "../components/Confirm";
import EditDeviceSheet, { type DeviceForm } from "../components/EditDeviceSheet";
import NameAvatar from "../components/NameAvatar";
import Feedback from "../components/Feedback";
import PageHeader from "../components/PageHeader";
import PageStack from "../components/PageStack";
import OnOff from "../components/OnOff";
import PageLoading from "../components/PageLoading";
import { translate, useT } from "../lib/i18n";

// untrusted: reaches only the services granted to it, never the remote login. external: Nord lists it as a device of
// another account, so it is untrusted for good (the switch is locked).
type Device = {
  name: string;
  public_key: string;
  enabled: boolean;
  services: string[];
  peer: Peer | null;
  avatar?: string | null;
  untrusted: boolean;
  external: boolean;
  meshnet?: "mine" | "theirs" | "both" | null; // set by the user for an external device: whose Meshnet the link belongs to
};

const wide = { display: "block", overflow: "visible", WebkitLineClamp: "none" } as const; // ItemDescription clamps to 2 lines
type State = { by_address?: boolean; vpn_up: boolean; peers_ok: boolean; devices: Device[]; available: Peer[] };
type Change = { applied: boolean };

function deviceStatus(d: Device, peersOk: boolean): string {
  if (!peersOk) return translate("devices.statusUnavailable");
  if (!d.peer) return translate("devices.notFound");
  return `${d.peer.ip} · ${d.peer.status || translate("devices.found")}`;
}

// Whose Meshnet the link belongs to. Nord does not report who invited whom (for the devices of another account both
// permission sets read the same), so the user sets it in "Edit device"; the devices of your own account have none.
function relation(d: Device): string {
  if (!d.external) return "";
  if (d.meshnet === "mine") return translate("devices.relMine");
  if (d.meshnet === "theirs") return translate("devices.relTheirs");
  return d.meshnet === "both" ? translate("devices.relBoth") : "";
}

export default function Devices() {
  const { t } = useT();
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState<Device | null>(null); // kept after closing so the sheet can slide out
  const [editOpen, setEditOpen] = useState(false);

  const load = useCallback(() => {
    apiGet<State>("/devices").then(setState).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  // Runs one change, then refetches (peer status is resolved live by the backend).
  const change = async (run: () => Promise<Change>, doneMsg?: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await run();
      toast({ description: r.applied ? (doneMsg ?? t("devices.applied")) : t("devices.deferred") });
    } catch (e) {
      setError(String(e));
    } finally {
      load();
      setBusy(false);
    }
  };

  // The sheet shows its own error, so this resolves to a message instead of using the page error.
  const editDevice = async (original: Device, f: DeviceForm): Promise<string | null> => {
    setBusy(true);
    try {
      await apiPost<Change>(`/devices/${original.name}/edit`, {
        name: f.name,
        meshnet: f.meshnet,
        ...(f.avatarChanged ? (f.avatar ? { avatar: f.avatar } : { clear_avatar: true }) : {}),
      });
      toast({ description: t("devices.updated", { name: f.name }) });
      load();
      return null;
    } catch (e) {
      return String(e);
    } finally {
      setBusy(false);
    }
  };

  if (!state) return <PageLoading title={t("devices.title")} error={error} />;

  return (
    <PageStack>
      <PageHeader
        title={t("devices.title")}
        subtitle={state.vpn_up ? t("devices.subtitleUp") : t("devices.subtitleDown")}
        action={
          <Button variant="default" size="small" disabled={busy} onClick={() => setSheetOpen(true)}>
            <Plus /> {t("devices.add")}
          </Button>
        }
      />
      <Feedback error={error} />

      {state.devices.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyDescription>{t("devices.none")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      {state.devices.map((d) => (
        <Card key={d.public_key}>
          <ItemGroup>
            <Item size="sm">
              <ItemMedia>
                <NameAvatar name={d.name} src={d.avatar} size={40} outlined />
              </ItemMedia>
              <ItemContent>
                <ItemTitle>
                  {d.name} {d.untrusted && <Tag variant="alert">{t("tag.untrusted").toUpperCase()}</Tag>}{" "}
                  {d.external && (d.meshnet === "mine" || d.meshnet === "both") && <Tag variant="default">{t("devices.relTagYours").toUpperCase()}</Tag>}{" "}
                  {d.external && (d.meshnet === "theirs" || d.meshnet === "both") && <Tag variant="ready">{t("devices.relTagTheirs").toUpperCase()}</Tag>}
                </ItemTitle>
                <ItemDescription>{deviceStatus(d, state.peers_ok)}</ItemDescription>
                {relation(d) && <ItemDescription style={wide}>{relation(d)}</ItemDescription>}
                <ItemDescription>{t("devices.servicesLine", { list: d.services.length ? d.services.join(", ") : t("devices.servicesNone") })}</ItemDescription>
              </ItemContent>
              <ItemActions>
                <Button variant="default" size="mini" disabled={busy} aria-label={t("devices.edit")} tooltip={t("devices.edit")} onClick={() => { setEditing(d); setEditOpen(true); }}>
                  <Pencil />
                </Button>
                <Confirm
                  title={t("devices.removeTitle", { name: d.name })}
                  description={t("devices.removeDescription")}
                  actionLabel={t("devices.removeAction")}
          destructive
                  onConfirm={() => change(() => apiDelete<Change>(`/devices/${d.name}`), t("devices.removed"))}
                  trigger={(open) => (
                    <Button variant="destructive" size="small" disabled={busy} onClick={open}>
                      {t("devices.removeAction")}
                    </Button>
                  )}
                />
              </ItemActions>
            </Item>
            <ItemSeparator />
            <Item size="sm">
              <ItemContent>
                <ItemTitle>{d.untrusted ? t("devices.activeTitle") : t("devices.remoteAccess")}</ItemTitle>
                {d.untrusted && (
                  <ItemDescription style={wide}>{t("devices.activeDescription")}</ItemDescription>
                )}
              </ItemContent>
              <ItemActions>
                <OnOff
                  label={d.untrusted ? t("devices.activeLabel", { name: d.name }) : t("devices.remoteLabel", { name: d.name })}
                  value={d.enabled}
                  disabled={busy}
                  onChange={(v) => change(() => apiPost<Change>(`/devices/${d.name}/enabled`, { enabled: v }))}
                />
              </ItemActions>
            </Item>
            <ItemSeparator />
            <Item size="sm">
              <ItemContent>
                <ItemTitle>{t("devices.untrustedTitle")}</ItemTitle>
                <ItemDescription style={wide}>
                  {d.external ? t("devices.untrustedExternal") : t("devices.untrustedDescription")}
                </ItemDescription>
              </ItemContent>
              <ItemActions>
                <Confirm
                  destructive={!d.untrusted}
                  title={d.untrusted ? t("devices.makeTrustedTitle", { name: d.name }) : t("devices.makeUntrustedTitle", { name: d.name })}
                  description={
                    d.untrusted
                      ? t("devices.makeTrustedDescription")
                      : d.services.length
                        ? t("devices.makeUntrustedWithServices", { list: d.services.join(", ") })
                        : t("devices.makeUntrustedNoServices")
                  }
                  actionLabel={d.untrusted ? t("devices.makeTrustedAction") : t("devices.makeUntrustedAction")}
                  onConfirm={() =>
                    change(
                      () => apiPost<Change>(`/devices/${d.name}/untrusted`, { untrusted: !d.untrusted }),
                      d.untrusted ? t("devices.becameTrusted") : t("devices.becameUntrusted"),
                    )
                  }
                  trigger={(open) => (
                    <OnOff
                      label={t("devices.untrustedLabel", { name: d.name })}
                      value={d.untrusted}
                      // Not `disabled` for an external device: PDS draws a disabled switch grey, which reads as "off".
                      // It stays on and says why it cannot change (the backend refuses the change too).
                      disabled={busy}
                      onChange={() => (d.external ? toast({ description: t("devices.externalToast") }) : open())}
                    />
                  )}
                />
              </ItemActions>
            </Item>
          </ItemGroup>
        </Card>
      ))}

      {editing && (
        <EditDeviceSheet
          key={editing.public_key}
          open={editOpen}
          onOpenChange={setEditOpen}
          device={editing}
          existingNames={state.devices.map((d) => d.name).filter((n) => n !== editing.name)}
          onSubmit={(f) => editDevice(editing, f)}
        />
      )}
      <AddDeviceSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        peersOk={state.peers_ok}
        available={state.available}
        busy={busy}
        byAddress={!!state.by_address}
        onAddAddress={(address, name) => {
          setSheetOpen(false);
          change(() => apiPost<Change>("/devices/by-address", { address, ...(name ? { name } : {}) }), t("devices.added"));
        }}
        onAdd={(peer) => {
          setSheetOpen(false);
          change(
            () => apiPost<Change>("/devices", { public_key: peer.public_key }),
            t("devices.added"),
          );
        }}
      />
    </PageStack>
  );
}
