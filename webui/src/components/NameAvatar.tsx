// PDS Avatar showing the uploaded picture, or the initials of the name while there is none (or it fails to load).
import { Avatar, AvatarFallback, AvatarImage } from "@workspace/pds/components/ui/avatar";

const initialsOf = (name: string) =>
  name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase() || "?";

export default function NameAvatar({
  name,
  src,
  size = 40,
  ring = false,
  outlined = false,
  dim = false,
}: {
  name: string;
  src?: string | null;
  size?: number;
  ring?: boolean; // card-colored outline, used where the avatar overlaps a colored banner
  outlined?: boolean; // thin border, so the empty fallback circle stays visible on a same-colored background
  dim?: boolean; // faded, for disabled items
}) {
  return (
    <Avatar
      style={{
        width: size,
        height: size,
        opacity: dim ? 0.55 : 1,
        ...(ring ? { boxShadow: "0 0 0 3px var(--color-card)" } : outlined ? { boxShadow: "0 0 0 1px var(--pds-container-border-color)" } : {}),
      }}
    >
      {src && <AvatarImage src={src} alt="" />}
      <AvatarFallback style={{ fontSize: size * 0.38, fontWeight: 500 }}>{initialsOf(name)}</AvatarFallback>
    </Avatar>
  );
}
