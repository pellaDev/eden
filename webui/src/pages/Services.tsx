// Services whitelisted directly on Meshnet, one card each: a global on/off plus a per-device grant.
// Every change is saved to eden.json and, if the VPN is up, applied immediately by the backend (vpn-reload).
// This page renders its cards as direct children of the PDS grid canvas (see GRID_PAGES in layout/Sidebar.tsx);
// header, errors and the empty state span all the columns.
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Plus } from "lucide-react";
import { Button } from "@workspace/pds/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "@workspace/pds/components/ui/empty";
import { toast } from "@workspace/pds/hooks/use-toast";
import { apiDelete, apiGet, apiPost } from "../lib/api";
import ServiceSheet, { type ServiceForm } from "../components/ServiceSheet";
import Feedback from "../components/Feedback";
import PageHeader from "../components/PageHeader";
import PageLoading from "../components/PageLoading";
import ServiceCard, { type DeviceGrant, type Service } from "../components/ServiceCard";
import RemoteServiceCard, { type RemoteService } from "../components/RemoteServiceCard";
import RemoteServiceSheet, { type RemotePeer, type RemoteServiceForm } from "../components/RemoteServiceSheet";
import { useT } from "../lib/i18n";
import { useWindows } from "../lib/platform";

type State = { vpn_up: boolean; mesh_ip?: string | null; services: Service[]; devices: DeviceGrant[] };
type Change = State & { applied: boolean };
type RemoteState = { peers_ok: boolean; services: RemoteService[]; peers: RemotePeer[] };

const fullRow = { gridColumn: "1 / -1" } as const;

export default function Services() {
  const { t } = useT();
  const windows = useWindows();
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState<Service | null>(null); // kept after closing so the sheet can slide out
  const [editOpen, setEditOpen] = useState(false);

  // Remote services: ports other devices offer to this computer (a bookmark list; nothing to apply to the firewall).
  const [remote, setRemote] = useState<RemoteState | null>(null);
  const [remoteSheetOpen, setRemoteSheetOpen] = useState(false);
  const [remoteEditing, setRemoteEditing] = useState<RemoteService | null>(null);
  const [remoteEditOpen, setRemoteEditOpen] = useState(false);

  const load = useCallback(() => {
    apiGet<State>("/services").then(setState).catch((e) => setError(String(e)));
    apiGet<RemoteState>("/remote-services").then(setRemote).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  // Coming back from the editor window: refresh, so a port just added to the file stops being flagged.
  useEffect(() => {
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  // Runs one change; the backend answers with the full new state.
  const run = async (call: () => Promise<Change>, doneMsg?: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await call();
      setState(r);
      toast({ description: doneMsg ?? (r.applied ? t("devices.applied") : t("devices.deferred")) });
    } catch (e) {
      setError(String(e));
      load(); // resync with whatever the backend actually has
    } finally {
      setBusy(false);
    }
  };

  // Opens /etc/eden/allowed_ports in a terminal with sudoedit; errors (no terminal found) carry the manual command.
  const openPortsFile = async () => {
    setError(null);
    try {
      await apiPost<{ ok: boolean }>("/allowed-ports/open");
      toast({ description: t(windows ? "services.fileOpened.win" : "services.fileOpened") });
    } catch (e) {
      setError(String(e));
    }
  };

  // The Sheet shows the error itself, so this resolves to a message instead of using the page error.
  const addService = async (f: ServiceForm): Promise<string | null> => {
    setBusy(true);
    try {
      const svc = { name: f.name, port: f.port, note: f.note, avatar: f.avatar, forward: f.forward };
      const r = await apiPost<Change>("/services", svc);
      setState(r);
      toast({ description: t("services.added", { name: svc.name }) });
      return null;
    } catch (e) {
      return String(e);
    } finally {
      setBusy(false);
    }
  };

  // Same idea for editing. The picture is sent only if it was touched: a new one, or "remove".
  const editService = async (original: Service, f: ServiceForm): Promise<string | null> => {
    setBusy(true);
    try {
      const body = {
        name: f.name,
        port: f.port,
        note: f.note,
        forward: f.forward,
        ...(f.avatarChanged ? (f.avatar ? { avatar: f.avatar } : { clear_avatar: true }) : {}),
      };
      const r = await apiPost<Change>(`/services/${original.name}/edit`, body);
      setState(r);
      toast({
        description:
          f.port !== original.port
            ? t("services.updatedPort", { name: f.name })
            : t("services.updated", { name: f.name }),
      });
      return null;
    } catch (e) {
      return String(e);
    } finally {
      setBusy(false);
    }
  };

  // Remote services: same pattern as above; the sheet shows its own error.
  const remoteCall = async (call: () => Promise<RemoteState>, doneMsg: string): Promise<string | null> => {
    setBusy(true);
    try {
      setRemote(await call());
      toast({ description: doneMsg });
      return null;
    } catch (e) {
      return String(e);
    } finally {
      setBusy(false);
    }
  };
  const addRemote = (f: RemoteServiceForm) =>
    remoteCall(() => apiPost<RemoteState>("/remote-services", f), t("services.remoteAdded", { name: f.name }));
  const editRemote = (original: RemoteService, f: RemoteServiceForm) =>
    remoteCall(() => apiPost<RemoteState>(`/remote-services/${original.name}/edit`, f), t("services.remoteUpdated", { name: f.name }));
  const deleteRemote = async (name: string) => {
    const err = await remoteCall(() => apiDelete<RemoteState>(`/remote-services/${name}`), t("services.remoteDeleted", { name }));
    if (err) setError(err);
  };

  // ---- drag to reorder -------------------------------------------------------------------------------------
  // Native HTML5 drag and drop (mouse; no touch). While a card is dragged the grid is reordered live in `order`;
  // when the drag ends the new order is saved (order of the `services` array in eden.json) and, if saving fails,
  // the page reloads the stored order. Dropping outside any card keeps the arrangement shown; Esc does not cancel.
  const [order, setOrder] = useState<string[] | null>(null); // names in display order, only while dragging/saving
  const [dragName, setDragName] = useState<string | null>(null);
  const orderRef = useRef<string[] | null>(null);
  const dragRef = useRef<string | null>(null);

  const startDrag = (name: string, e: DragEvent) => {
    const card = (e.currentTarget as HTMLElement).closest("[data-service-card]");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", name); // Firefox starts a drag only when some data is set
    if (card) {
      const r = card.getBoundingClientRect();
      e.dataTransfer.setDragImage(card, e.clientX - r.left, e.clientY - r.top); // the whole card follows the pointer
    }
    dragRef.current = name;
    orderRef.current = (state?.services ?? []).map((s) => s.name);
    // After the browser has taken its drag image: dimming the card at once would dim the picture too.
    setTimeout(() => {
      setOrder(orderRef.current);
      setDragName(dragRef.current);
    }, 0);
  };

  const dragOverCard = (target: string) => {
    const cur = orderRef.current;
    const drag = dragRef.current;
    if (!cur || !drag) return;
    const from = cur.indexOf(drag);
    const to = cur.indexOf(target);
    if (from < 0 || to < 0 || from === to) return;
    const next = [...cur];
    next.splice(from, 1);
    next.splice(to, 0, drag);
    orderRef.current = next;
    setOrder(next);
  };

  const endDrag = async () => {
    const next = orderRef.current;
    dragRef.current = null;
    orderRef.current = null;
    setDragName(null);
    const before = (state?.services ?? []).map((s) => s.name).join("\n");
    if (!next || next.join("\n") === before) {
      setOrder(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setState(await apiPost<State>("/services-order", { names: next }));
    } catch (e) {
      setError(String(e));
      load(); // resync with the order the backend actually has
    } finally {
      setOrder(null);
      setBusy(false);
    }
  };

  if (!state) return <PageLoading title={t("services.title")} error={error} />;

  // Display order: the live one while dragging/saving (services created meanwhile go last), otherwise the stored one.
  const shown = order
    ? [
        ...order.map((n) => state.services.find((s) => s.name === n)).filter((s): s is Service => !!s),
        ...state.services.filter((s) => !order.includes(s.name)),
      ]
    : state.services;

  return (
    <>
      <div style={fullRow}>
        <PageHeader
          title={t("services.title")}
          subtitle={state.vpn_up ? t("services.subtitleUp") : t("services.subtitleDown")}
          action={
            <Button variant="default" size="small" disabled={busy} onClick={() => setSheetOpen(true)}>
              <Plus /> {t("services.add")}
            </Button>
          }
        />
      </div>

      {error && (
        <div style={fullRow}>
          <Feedback error={error} />
        </div>
      )}

      {state.services.length === 0 && (
        <div style={fullRow}>
          <Empty>
            <EmptyHeader>
              <EmptyDescription>{t("services.empty")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </div>
      )}

      {shown.map((svc) => (
        <ServiceCard
          key={svc.name}
          svc={svc}
          meshIp={state.mesh_ip ?? null}
          dnd={{
            dragging: dragName === svc.name,
            onHandleDragStart: (e) => startDrag(svc.name, e),
            onHandleDragEnd: endDrag,
            onCardDragEnter: () => dragOverCard(svc.name),
            onCardDragOver: (e) => {
              if (!dragRef.current) return; // not one of our cards (a file, a link): leave the browser default
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
            },
            onCardDrop: (e) => e.preventDefault(), // stops Firefox from "opening" the dragged text; the save happens on drag end
          }}
          devices={state.devices}
          busy={busy}
          onToggle={(v) => run(() => apiPost<Change>(`/services/${svc.name}`, { enabled: v }))}
          onGrant={(device, granted) => run(() => apiPost<Change>(`/devices/${device}/services/${svc.name}`, { granted }))}
          onDelete={() => run(() => apiDelete<Change>(`/services/${svc.name}`), t("services.deleted", { name: svc.name }))}
          onEdit={() => {
            setEditing(svc);
            setEditOpen(true);
          }}
          onForward={(v) => run(() => apiPost<Change>(`/services/${svc.name}/edit`, { forward: v }))}
          onOpenPortsFile={openPortsFile}
        />
      ))}

      <div style={{ ...fullRow, paddingTop: "1rem" }}>
        <PageHeader
          title={t("services.remoteTitle")}
          subtitle={t("services.remoteSubtitle")}
          action={
            <Button variant="default" size="small" disabled={busy} onClick={() => setRemoteSheetOpen(true)}>
              <Plus /> {t("services.remoteAdd")}
            </Button>
          }
        />
      </div>
      {remote && remote.services.length === 0 && (
        <div style={fullRow}>
          <Empty>
            <EmptyHeader>
              <EmptyDescription>{t("services.remoteEmpty")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </div>
      )}
      {remote?.services.map((rs) => (
        <RemoteServiceCard
          key={rs.name}
          svc={rs}
          peersOk={remote.peers_ok}
          busy={busy}
          onEdit={() => {
            setRemoteEditing(rs);
            setRemoteEditOpen(true);
          }}
          onDelete={() => deleteRemote(rs.name)}
        />
      ))}
      {remote && (
        <RemoteServiceSheet
          mode="add"
          open={remoteSheetOpen}
          onOpenChange={setRemoteSheetOpen}
          peers={remote.peers}
          peersOk={remote.peers_ok}
          existingNames={remote.services.map((r) => r.name)}
          onSubmit={addRemote}
        />
      )}
      {remote && remoteEditing && (
        <RemoteServiceSheet
          key={remoteEditing.name}
          mode="edit"
          open={remoteEditOpen}
          onOpenChange={setRemoteEditOpen}
          service={remoteEditing}
          peers={remote.peers}
          peersOk={remote.peers_ok}
          existingNames={remote.services.map((r) => r.name).filter((n) => n !== remoteEditing.name)}
          onSubmit={(f) => editRemote(remoteEditing, f)}
        />
      )}

      <ServiceSheet
        mode="add"
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        existingNames={state.services.map((s) => s.name)}
        onSubmit={addService}
      />
      {editing && (
        <ServiceSheet
          key={editing.name}
          mode="edit"
          open={editOpen}
          onOpenChange={setEditOpen}
          service={editing}
          existingNames={state.services.map((s) => s.name).filter((n) => n !== editing.name)}
          onSubmit={(f) => editService(editing, f)}
        />
      )}
    </>
  );
}
