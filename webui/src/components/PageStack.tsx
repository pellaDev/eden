// The vertical column every page is made of: one PDS Stack with the spacing the pages used before (0.5rem).
import type { ReactNode } from "react";
import { Stack } from "@workspace/pds/components/ui/layout";

export default function PageStack({ children }: { children: ReactNode }) {
  return <Stack gap="ss">{children}</Stack>;
}
