/** features/inbox API 클라이언트 — Story 4.5. */

import { apiFetch } from "@/lib/api-client";
import type {
  ActivePopup,
  InboxFilter,
  InboxListResponse,
  InboxPreviewResponse,
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

/** GET /api/v1/me/inbox/preview — 쪽지함 미리보기 드롭다운(서버가 max_count 강제). */
export async function fetchInboxPreview(): Promise<InboxPreviewResponse> {
  return apiFetch<InboxPreviewResponse>("/api/v1/me/inbox/preview");
}

/** GET /api/v1/me/popups/active?device={pc|mobile} — Story 7.2 v2.
 *
 * 캐러셀 노출 후보 배열. 매칭 0건은 빈 배열. 디바이스 필터 필수.
 */
export async function fetchActivePopups(
  device: "pc" | "mobile",
): Promise<ActivePopup[]> {
  const result = await apiFetch<ActivePopup[] | undefined>(
    `/api/v1/me/popups/active?device=${device}`,
  );
  return result ?? [];
}
