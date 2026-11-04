// One setting with a small set of mutually exclusive choices (a PDS Toggle group in an Item row), shared by
// Impostazioni and Notifiche. Since PDS 1.10 the group lives in the "toggle" module: <Toggle type="single"> is the
// group, <Toggle asItem> an option. On a phone the group takes the full width and wraps by itself.
import { Item, ItemActions, ItemContent, ItemDescription, ItemTitle } from "@workspace/pds/components/ui/item";
import { Toggle } from "@workspace/pds/components/ui/toggle";

export default function ToggleRow({
  label,
  description,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string;
  description?: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Item size="sm">
      {/* A basis lets long descriptions wrap in their own column; the controls drop below when space is short */}
      <ItemContent style={{ flex: "1 1 16rem", minWidth: 0 }}>
        <ItemTitle>{label}</ItemTitle>
        {description && (
          // ItemDescription clamps to two lines by default: undo it, these texts must be read in full
          <ItemDescription style={{ display: "block", overflow: "visible", WebkitLineClamp: "none" }}>{description}</ItemDescription>
        )}
      </ItemContent>
      <ItemActions>
        {/* Clicking the active item yields an empty value: ignored, one option stays selected */}
        <Toggle type="single" size="sm" value={value} disabled={disabled} onValueChange={(v: string) => v && onChange(v)}>
          {options.map((o) => (
            <Toggle asItem key={o.value} value={o.value}>
              {o.label}
            </Toggle>
          ))}
        </Toggle>
      </ItemActions>
    </Item>
  );
}
