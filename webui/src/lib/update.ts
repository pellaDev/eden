// Update checks for the two things Eden can refresh on its own: itself (GitHub releases) and NordVPN
// (Nord's yum repository). The backend caches the metadata, so calling this per page mount is cheap.
import { apiGet } from "./api";

export type UpdateInfo = { installed?: string; latest?: string; available?: boolean; dev?: boolean; error?: string };
export type UpdateStatus = { eden: UpdateInfo; nordvpn: UpdateInfo };

export function updateStatus(fresh = false): Promise<UpdateStatus> {
  return apiGet<UpdateStatus>(fresh ? "/update/status?fresh=1" : "/update/status");
}
