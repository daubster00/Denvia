/** features/inbox API 클라이언트 — Story 4.5. */

import { apiFetch } from "@/lib/api-client";
import type {
  ActivePopup,
  InboxFilter,
  InboxListResponse,
  UnreadCountResponse,
} from "./types";

/** GET /api/v1/me/inbox */
export async function fetchInbox(
  page: number,
  perPage: number,
  filter: InboxFilter,
): Promise<InboxListResponse> {
  const qs = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
    filter,
  });
  return apiFetch<InboxListResponse>(`/api/v1/me/inbox?${qs.toString()}`);
}

/** PATCH /api/v1/me/inbox/{id}/read — 204 응답. */
export async function markInboxRead(messageId: number): Promise<void> {
  await apiFetch<void>(`/api/v1/me/inbox/${messageId}/read`, {
    method: "PATCH",
  });
}

/** GET /api/v1/me/inbox/unread-count */
export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  return apiFetch<UnreadCountResponse>("/api/v1/me/inbox/unread-count");
}

/** GET /api/v1/me/popups/active — 매칭 0건이면 null(204). */
export async function fetchActivePopup(): Promise<ActivePopup | null> {
  const result = await apiFetch<ActivePopup | undefined>(
    "/api/v1/me/popups/active",
  );
  // apiFetch는 204를 undefined로 반환 → TanStack Query는 undefined 반환을 막으므로 null 정규화
  return result ?? null;
}

/** POST /api/v1/me/popups/{id}/seen — 204 응답. */
export async function markPopupSeen(popupId: number): Promise<void> {
  await apiFetch<void>(`/api/v1/me/popups/${popupId}/seen`, {
    method: "POST",
  });
}
