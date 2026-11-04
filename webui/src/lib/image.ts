// Avatar upload helper: the browser crops the picked image to a centered square, scales it down and
// returns a small data URL, so the backend only ever stores a few KB per service.
import { translate } from "./i18n";

const MAX_INPUT_BYTES = 5 * 1024 * 1024;
export const AVATAR_TYPES = "image/png,image/jpeg,image/webp,image/gif";

export async function fileToAvatar(file: File, size = 128): Promise<string> {
  if (!AVATAR_TYPES.split(",").includes(file.type)) throw new Error(translate("image.unsupported"));
  if (file.size > MAX_INPUT_BYTES) throw new Error(translate("image.tooBig"));

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error(translate("image.unreadable"));
  }
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(translate("image.unprocessable"));
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, size, size);
  bitmap.close();

  // WebP is smaller; some browsers silently fall back to PNG, which is fine too.
  const webp = canvas.toDataURL("image/webp", 0.85);
  return webp.startsWith("data:image/webp") ? webp : canvas.toDataURL("image/png");
}
