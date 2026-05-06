/** Admin 고객문의 — 한국어 라벨. */

import type { InquiryStatus } from "@/features/admin-support/api/inquiries";

export const INQUIRY_STATUS_LABELS: Record<InquiryStatus, string> = {
  open: "신규",
  in_progress: "처리중",
  resolved: "완료",
};

export function formatInquiryStatus(status: InquiryStatus): string {
  return INQUIRY_STATUS_LABELS[status] ?? status;
}
