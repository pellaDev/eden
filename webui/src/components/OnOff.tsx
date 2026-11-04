// Boolean control shared by Services and Devices: a controlled PDS Switch.
// The parent owns the value; it only changes after the backend answered and the state was refetched.
import { Switch } from "@workspace/pds/components/ui/switch";

export default function OnOff({
  value,
  disabled,
  onChange,
  label,
  text,
}: {
  value: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
  label: string; // accessible name: the switch has no visible text of its own
  text?: string; // optional visible caption next to the switch
}) {
  return <Switch checked={value} disabled={disabled} aria-label={label} label={text} onChange={(e) => onChange(e.target.checked)} />;
}
