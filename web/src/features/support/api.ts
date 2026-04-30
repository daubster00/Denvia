/** features/support API 클라이언트 — Story 4.5 (F-504). */

import { apiFetch } from "@/lib/api-client";

interface InquirySubmitResponse {
  inquiry_id: number;
}

/** POST /api/v1/support/inquiries — 인증 필수, 분당 3회 레이트 리밋. */
export async function postInquiry(
  subject: string,
  body: string,
): Promise<InquirySubmitResponse> {
  return apiFetch<InquirySubmitResponse>("/api/v1/support/inquiries", {
    method: "POST",
    body: JSON.stringify({ subject, body }),
  });
}
