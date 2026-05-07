/** features/inbox 타입 정의 — Story 4.5. */

export type InboxMessageType = "notice" | "system" | "billing";

export type InboxFilter = "all" | "unread";

export interface InboxItem {
  message_id: number;
  type: InboxMessageType;
  title: string;
  body_html_safe: string;
  is_read: boolean;
  created_at: string;
  notice_id: number | null;
  popup_id: number | null;
}

export interface InboxListResponse {
  items: InboxItem[];
  page: number;
  per_page: number;
  total: number;
  unread_count: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export type PopupTargetDevice = "pc" | "mobile" | "both";
export type PopupType = "image" | "editor";

export interface ActivePopup {
  popup_id: number;
  title: string;
  popup_type: PopupType;
  image_url: string | null;
  body_html_safe: string | null;
  link_url: string | null;
  display_end: string;
}

export interface InboxPreviewItem {
  message_id: number;
  type: InboxMessageType;
  title: string;
  is_read: boolean;
  created_at: string;
}

export interface InboxPreviewResponse {
  items: InboxPreviewItem[];
  max_count: number;
}
