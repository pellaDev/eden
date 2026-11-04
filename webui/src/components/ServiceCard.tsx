// One service as a card. The banner takes the brand color while the service is on and turns grey when it is
// off. Below: the Eden devices with their access switch; a device disabled in Devices is greyed out and
// its switch is locked (the stored grant stays visible but cannot open the port).
import { NavLink } from "react-router-dom";
import type { DragEvent } from "react";
import { Copy, FileText, GripVertical, Pencil, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Badge } from "@workspace/pds/components/ui/badge";
import { Button } from "@workspace/pds/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@workspace/pds/components/ui/card";
import { Row, Stack } from "@workspace/pds/components/ui/layout";
import { Separator } from "@workspace/pds/components/ui/separator";
import { Tag } from "@workspace/pds/components/ui/tag";
import { toast } from "@workspace/pds/hooks/use-toast";
import { copyText } from "../lib/clipboard";
import Confirm from "./Confirm";
import NameAvatar from "./NameAvatar";
import OnOff from "./OnOff";
import { useT } from "../lib/i18n";
import { useWindows } from "../lib/platform";

export type Service = {
  name: string;
  port: number;
  enabled: boolean;
  note: string;
  avatar?: string | null; // anything usable as <img src>: a data URL or a backend URL
  port_allowed?: boolean; // false: the root helper's allowed ports do not include this port, so it can never open
  forward?: boolean; // the service listens only on 127.0.0.1: Eden forwards the Meshnet address to it
  // What the forwarder says about this service's route: null = not forwarded or forwarder not running (VPN down)
  forward_status?: { state: "listening" | "error" | "idle"; detail?: string } | null;
};
// Drag-to-reorder hooks, owned by the page (Services.tsx): the card only wires them to its handle and its box.
export type CardDnd = {
  dragging: boolean; // this card is the one being dragged
  onHandleDragStart: (e: DragEvent) => void;
  onHandleDragEnd: () => void;
  onCardDragEnter: () => void; // something is dragged over this card
  onCardDragOver: (e: DragEvent) => void;
  onCardDrop: (e: DragEvent) => void;
};
export type DeviceGrant = { name: string; enabled: boolean; services: string[]; avatar?: string | null; untrusted?: boolean };

export default function ServiceCard({
  svc,
  devices,
  busy,
  onToggle,
  onGrant,
  onDelete,
  onEdit,
  onForward,
  onOpenPortsFile,
  meshIp,
  dnd,
}: {
  svc: Service;
  devices: DeviceGrant[];
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onGrant: (device: string, granted: boolean) => void;
  onDelete: () => void;
  onEdit: () => void;
  onForward: (forward: boolean) => void;
  onOpenPortsFile: () => void; // opens /etc/eden/allowed_ports for editing (sudoedit in a terminal, see the backend)
  meshIp?: string | null; // the Eden computer's Meshnet address; null while the VPN is down
  dnd?: CardDnd;
}) {
  const { t } = useT();
  const windows = useWindows();
  // The exact address a Meshnet device uses to reach this service (a forwarded service listens on the same port).
  const address = meshIp ? `${meshIp}:${svc.port}` : null;
  const copyAddress = async () => {
    if (!address) return;
    const ok = await copyText(address);
    toast({ description: ok ? t("service.copied", { address }) : t("service.copyFailed") });
  };
  const blocked = svc.port_allowed === false;
  const live = svc.enabled && !blocked; // "on" in eden.json is not enough: a blocked port stays closed
  // The port is really open only for devices that are enabled AND granted, while the service is on.
  const openTo = devices.filter((d) => d.enabled && d.services.includes(svc.name)).length;
  const fwd = svc.forward ? svc.forward_status : null;
  const fwdError = live && fwd?.state === "error";   // the firewall may be open, but nothing is listening behind it
  const status = blocked
    ? t("service.statusBlocked")
    : !svc.enabled
      ? t("service.statusClosed")
      : openTo === 0
        ? t("service.statusNoDevice")
        : fwdError
          ? t("service.statusForwardDown")
          : (openTo === 1 ? t("service.statusOpenOne") : t("service.statusOpenMany", { n: openTo })) +
            (fwd?.state === "listening" ? t("service.forwardActive") : "");

  const tone = live ? "var(--color-primary)" : "var(--color-gray)";
  const banner = [
    "radial-gradient(circle at 88% 30%, color-mix(in srgb, white 26%, transparent) 0 2.4rem, transparent 2.45rem)",
    "radial-gradient(circle at 70% 95%, color-mix(in srgb, white 16%, transparent) 0 1.7rem, transparent 1.75rem)",
    `linear-gradient(135deg, ${tone}, color-mix(in srgb, ${tone} 45%, var(--color-card)))`,
  ].join(", ");

  return (
    <Card
      data-service-card=""
      style={{
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        opacity: dnd?.dragging ? 0.45 : 1,
        transition: "opacity 120ms ease",
      }}
      onDragEnter={dnd?.onCardDragEnter}
      onDragOver={dnd?.onCardDragOver}
      onDrop={dnd?.onCardDrop}
    >
      <div aria-hidden="true" style={{ height: "4.5rem", background: banner, transition: "background 200ms ease" }} />
      {dnd && (
        // The handle is a span (asChild) on purpose: Firefox does not start a drag from inside a <button>.
        <Button asChild size="mini" variant="default">
          <span
            role="button"
            draggable={!busy}
            aria-label={t("service.dragLabel", { name: svc.name })}
            title={t("service.drag")}
            onDragStart={dnd.onHandleDragStart}
            onDragEnd={dnd.onHandleDragEnd}
            style={{
              position: "absolute",
              top: "0.5rem",
              left: "0.5rem",
              zIndex: 1,
              cursor: busy ? "default" : "grab",
              background: "color-mix(in srgb, black 28%, transparent)",
              color: "white",
            }}
          >
            <GripVertical />
          </span>
        </Button>
      )}

      <CardHeader style={{ paddingTop: 0 }}>
        {/* The avatar is pulled up over the banner by its own margin. The switch is NOT pulled with it and is aligned to
            the top of this row: on a phone PDS gives it a 44px touch height, and bottom-aligning that to the avatar
            pushed its top edge up into the banner. */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div style={{ marginTop: "-2.25rem" }}>
            <NameAvatar name={svc.name} src={svc.avatar} size={64} ring />
          </div>
          <div style={{ marginTop: "0.25rem" }}>
            <OnOff
              label={t("service.globalLabel", { name: svc.name })}
              text={svc.enabled ? t("service.on") : t("service.off")}
              value={svc.enabled}
              disabled={busy || (blocked && !svc.enabled)}
              onChange={onToggle}
            />
          </div>
        </div>
        <CardTitle style={{ fontSize: "1.125rem" }}>{svc.name}</CardTitle>
        <CardDescription>{svc.note || t("service.noNote")}</CardDescription>
        <Row gap="ss" className="py-1">
          <Tag variant={live ? "ready" : "disabled"}>{address ?? t("service.vpnOffPort", { port: svc.port })}</Tag>
          {address && (
            <Button variant="default" size="mini" aria-label={t("service.copyAddress")} tooltip={t("service.copyAddress")} onClick={copyAddress}>
              <Copy />
            </Button>
          )}
        </Row>
        {blocked && (
          <Alert variant="destructive">
            <AlertDescription>
              {t(windows ? "service.blockedAlert.win" : "service.blockedAlert")}
            </AlertDescription>
            <div style={{ paddingTop: "0.5rem" }}>
              <Button variant="default" size="small" onClick={onOpenPortsFile}>
                <FileText /> {t("service.openFile")}
              </Button>
            </div>
          </Alert>
        )}
      </CardHeader>

      <CardContent style={{ flex: 1 }}>
        <Separator style={{ marginBottom: "0.75rem" }} />
        {/* A plain div on purpose (decision 38): the switch must stay on the right, a Row would wrap it under the text */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div style={{ minWidth: 0 }}>
            <div className="text-sm">{t("service.forwardTitle")}</div>
            <div className="text-xs text-muted-foreground">{t("service.forwardHint")}</div>
          </div>
          <OnOff label={t("service.forwardLabel", { name: svc.name })} value={!!svc.forward} disabled={busy} onChange={onForward} />
        </div>
        {fwdError && (
          <Alert variant="destructive" style={{ marginBottom: "0.75rem" }}>
            <AlertDescription>{t("service.forwardError", { detail: fwd?.detail ?? t("service.unknownError") })}</AlertDescription>
          </Alert>
        )}
        <div className="text-xs text-muted-foreground" style={{ textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.5rem" }}>
          {t("service.deviceAccess")}
        </div>
        {devices.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("service.noDevices")}{" "}
            <Button variant="link" size="small" asChild>
              <NavLink to="/devices">{t("service.addOne")}</NavLink>
            </Button>
          </p>
        ) : (
          <Stack gap="ss">
            {devices.map((d) => (
              <Row key={d.name} gap="ss" className="justify-between">
                <Row gap="ss" className="min-w-0">
                  <NameAvatar name={d.name} src={d.avatar} size={28} outlined dim={!d.enabled} />
                  <span
                    className={d.enabled ? "text-sm" : "text-sm text-muted-foreground"}
                    style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {d.name}
                  </span>
                  {d.untrusted && <Tag variant="alert">untrusted</Tag>}
                  {!d.enabled && <Tag variant="disabled">{t("service.disabledTag")}</Tag>}
                </Row>
                <OnOff
                  label={`${d.name}: ${svc.name}`}
                  value={d.services.includes(svc.name)}
                  disabled={busy || !d.enabled}
                  onChange={(v) => onGrant(d.name, v)}
                />
              </Row>
            ))}
          </Stack>
        )}
      </CardContent>

      <CardFooter style={{ justifyContent: "space-between", gap: "0.5rem" }}>
        <Row gap="ss" className="text-xs text-muted-foreground">
          <Badge variant={blocked || fwdError ? "error" : !svc.enabled ? "disabled" : openTo > 0 ? "ready" : "alert"} aria-hidden="true" />
          <span>{status}</span>
        </Row>
        <Row gap="ss">
        <Button variant="default" size="mini" disabled={busy} aria-label={t("service.editLabel")} tooltip={t("service.editLabel")} onClick={onEdit}>
          <Pencil />
        </Button>
        <Confirm
          destructive
          title={t("service.deleteTitle", { name: svc.name })}
          description={t("service.deleteDescription")}
          actionLabel={t("service.delete")}
          onConfirm={onDelete}
          trigger={(open) => (
            <Button variant="destructive" size="mini" disabled={busy} aria-label={t("service.deleteLabel")} tooltip={t("service.deleteLabel")} onClick={open}>
              <Trash2 />
            </Button>
          )}
        />
        </Row>
      </CardFooter>
    </Card>
  );
}
