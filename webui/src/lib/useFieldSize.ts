// Size for every PDS Field: "lg" (3.5rem, comfortable for a finger) on a phone, "sm" (2.5rem) on desktop.
// PDS switches its own forms at 48rem (useIsMobile), so the fields follow the same breakpoint.
import { useIsMobile } from "@workspace/pds/hooks/use-mobile";

export function useFieldSize(): "sm" | "lg" {
  return useIsMobile() ? "lg" : "sm";
}
