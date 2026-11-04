// One remote service as a card: a port that ANOTHER device offers to this computer (the opposite direction of
// ServiceCard). Eden does not filter outgoing traffic, so there is no switch: the card shows where the service is,
// whether the device is really offering it (Nord's "Allows Incoming Traffic" from the peer) and opens it in a new tab.
import { Copy, ExternalLink, Pencil, Trash2 } from "lucide-react";
import { Badge } from "@workspace/pds/components/ui/badge";
import { Button } from "@workspace/pds/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@workspace/pds/components/ui/card";
import { Row } from "@workspace/pds/components/ui/layout";
import { Tag } from "@workspace/pds/components/ui/tag";
import { toast } from "@workspace/pds/hooks/use-toast";
import { copyText } from "../lib/clipboard";
import Confirm from "./Confirm";
import NameAvatar from "./NameAvatar";
import { useT } from "../lib/i18n";

export type RemoteService = {
  name: string;
  public_key: string;
  device: string; // Eden device name, else the peer's nickname/host name, else the name stored when it was last seen
  port: number;
  note: string;
  ip: string | null; // null while the peer list cannot be read or the device is not in the Meshnet
  address: string | null; // ip:port
  found: boolean; // the device is in the live peer list
  online: boolean;
  offered: boolean; // the device allows our incoming traffic: it is offering us its ports
};

export default function RemoteServiceCard({
  svc,
  peersOk,
  busy,
  onEdit,
  onDelete,
}: {
  svc: RemoteService;
  peersOk: boolean;
  busy: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useT();
  const ok = svc.found && svc.online && svc.offered;
  const status = !peersOk
    ? t("services.remoteVpnOff")
    : !svc.found
      ? t("services.remoteStatusMissing")
      : !svc.offered
        ? t("services.remoteStatusNotOffered")
        : !svc.online
          ? t("services.remoteStatusOffline")
          : t("services.remoteStatusOk");
  const copyAddress = async () => {
    if (!svc.address) return;
    const done = await copyText(svc.address);
    toast({ description: done ? t("service.copied", { address: svc.address }) : t("service.copyFailed") });
  };

  const tone = ok ? "var(--color-primary)" : "var(--color-gray)";
  const banner = [
    "radial-gradient(circle at 88% 30%, color-mix(in srgb, white 26%, transparent) 0 2.4rem, transparent 2.45rem)",
    "radial-gradient(circle at 70% 95%, color-mix(in srgb, white 16%, transparent) 0 1.7rem, transparent 1.75rem)",
    `linear-gradient(135deg, ${tone}, color-mix(in srgb, ${tone} 45%, var(--color-card)))`,
  ].join(", ");

  return (
    <Card style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div aria-hidden="true" style={{ height: "4.5rem", background: banner, transition: "background 200ms ease" }} />
      <CardHeader style={{ paddingTop: 0 }}>
        <div style={{ marginTop: "-2.25rem" }}>
          <NameAvatar name={svc.name} size={64} ring />
        </div>
        <CardTitle style={{ fontSize: "1.125rem" }}>{svc.name}</CardTitle>
        <CardDescription>{svc.note || t("services.remoteFrom", { device: svc.device })}</CardDescription>
        {svc.note && <p className="text-xs text-muted-foreground">{t("services.remoteFrom", { device: svc.device })}</p>}
        <Row gap="ss" className="py-1">
          <Tag variant={ok ? "ready" : "disabled"}>{svc.address ?? t("service.vpnOffPort", { port: svc.port })}</Tag>
          {svc.address && (
            <Button variant="default" size="mini" aria-label={t("service.copyAddress")} tooltip={t("service.copyAddress")} onClick={copyAddress}>
              <Copy />
            </Button>
          )}
          {svc.address && (
            <Button variant="default" size="mini" aria-label={t("services.remoteOpen")} tooltip={t("services.remoteOpen")} onClick={() => window.open(`http://${svc.address}/`, "_blank", "noopener,noreferrer")}>
              <ExternalLink />
            </Button>
          )}
        </Row>
      </CardHeader>
      <CardContent style={{ flex: 1 }} />
      <CardFooter style={{ justifyContent: "space-between", gap: "0.5rem" }}>
        <Row gap="ss" className="text-xs text-muted-foreground">
          <Badge variant={ok ? "ready" : peersOk && svc.found && !svc.offered ? "alert" : "disabled"} aria-hidden="true" />
          <span>{status}</span>
        </Row>
        <Row gap="ss">
          <Button variant="default" size="mini" disabled={busy} aria-label={t("services.remoteEditLabel")} tooltip={t("services.remoteEditLabel")} onClick={onEdit}>
            <Pencil />
          </Button>
          <Confirm
            destructive
            title={t("services.remoteDeleteTitle", { name: svc.name })}
            description={t("services.remoteDeleteDescription")}
            actionLabel={t("common.remove")}
            onConfirm={onDelete}
            trigger={(open) => (
              <Button variant="destructive" size="mini" disabled={busy} aria-label={t("services.remoteDeleteLabel")} tooltip={t("services.remoteDeleteLabel")} onClick={open}>
                <Trash2 />
              </Button>
            )}
          />
        </Row>
      </CardFooter>
    </Card>
  );
}
