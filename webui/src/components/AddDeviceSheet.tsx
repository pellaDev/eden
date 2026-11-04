// "Add device": a PDS Sheet from the right listing the live Meshnet peers that are not in Eden yet.
// A device is never typed in: it is picked from the live peer list and identified by its public key.
import { Info } from "lucide-react";
import { Alert, AlertDescription } from "@workspace/pds/components/ui/alert";
import { Button } from "@workspace/pds/components/ui/button";
import { Stack } from "@workspace/pds/components/ui/layout";
import { Empty, EmptyDescription, EmptyHeader } from "@workspace/pds/components/ui/empty";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemSeparator, ItemTitle } from "@workspace/pds/components/ui/item";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@workspace/pds/components/ui/sheet";
import { Tag } from "@workspace/pds/components/ui/tag";
import { Fragment, useState } from "react";
import { Field } from "@workspace/pds/components/ui/field";
import { useFieldSize } from "../lib/useFieldSize";
import { useT } from "../lib/i18n";
import NameAvatar from "./NameAvatar";

// external: Nord lists the peer under "External Peers" (a device of another Nord account).
// allow_in: we allow its incoming traffic (it can reach this computer). allows_in: it allows ours (it offers us its ports).
export type Peer = { nickname: string; hostname: string; ip: string; public_key: string; status: string; external?: boolean; allow_in?: boolean; allows_in?: boolean };

export default function AddDeviceSheet({
  open,
  onOpenChange,
  peersOk,
  available,
  busy,
  onAdd,
  byAddress = false,
  onAddAddress,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  peersOk: boolean; // false while the VPN is off: the peer list is not readable
  available: Peer[];
  busy: boolean;
  onAdd: (peer: Peer) => void;
  byAddress?: boolean; // Windows: there is no peer list, the device is typed by its Meshnet address
  onAddAddress?: (address: string, name: string) => void;
}) {
  const { t } = useT();
  const fieldSize = useFieldSize();
  const [address, setAddress] = useState("");
  const [name, setName] = useState("");
  const addressOk = /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}$/.test(address.trim());
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" style={{ width: "min(100vw, 28rem)", maxWidth: "28rem", overflowY: "auto" }}>
        <Stack gap="s">
          <SheetHeader>
            <SheetTitle>{t("addDevice.title")}</SheetTitle>
            <SheetDescription>{byAddress ? t("addDevice.byAddressDescription") : t("addDevice.description")}</SheetDescription>
          </SheetHeader>

          {byAddress && (
            <>
              <div>
                <Field size={fieldSize} label={t("addDevice.addressLabel")} value={address} inputMode="decimal" onChange={(e) => setAddress(e.target.value)} />
                <p className="text-xs" style={{ opacity: 0.7 }}>{t("addDevice.addressHelp")}</p>
              </div>
              <div>
                <Field size={fieldSize} label={t("common.name")} value={name} onChange={(e) => setName(e.target.value.toLowerCase())} />
                <p className="text-xs" style={{ opacity: 0.7 }}>{t("addDevice.nameHelp")}</p>
              </div>
              <Button variant="default" size="small" disabled={busy || !addressOk} onClick={() => { onAddAddress?.(address.trim(), name.trim()); setAddress(""); setName(""); }}>
                {t("common.add")}
              </Button>
            </>
          )}
          {!byAddress && !peersOk && (
            <Alert>
              <Info size={16} />
              <AlertDescription>{t("addDevice.vpnOff")}</AlertDescription>
            </Alert>
          )}
          {!byAddress && peersOk && available.length === 0 && (
            <Empty>
              <EmptyHeader>
                <EmptyDescription>{t("addDevice.none")}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          {!byAddress && available.length > 0 && (
            <ItemGroup>
              {available.map((p, i) => {
                // Nord prints "-" for a peer with no nickname: never show a dash as the name.
                const name = (p.nickname && p.nickname !== "-" ? p.nickname : "") || p.hostname;
                return (
                  <Fragment key={p.public_key}>
                    {i > 0 && <ItemSeparator />}
                    <Item size="sm">
                      <ItemMedia>
                        <NameAvatar name={name} size={36} outlined />
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>
                          {name} {p.external && <Tag variant="alert">{t("addDevice.external")}</Tag>}
                        </ItemTitle>
                        <ItemDescription>
                          {p.ip} · {p.status || "?"}
                        </ItemDescription>
                      </ItemContent>
                      <ItemActions>
                        <Button variant="default" size="small" disabled={busy} onClick={() => onAdd(p)}>
                          {t("common.add")}
                        </Button>
                      </ItemActions>
                    </Item>
                  </Fragment>
                );
              })}
            </ItemGroup>
          )}
        </Stack>
      </SheetContent>
    </Sheet>
  );
}
