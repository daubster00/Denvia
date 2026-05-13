/** features/support API 클라이언트 — 0030 1:1 문의 게시판화.
 *
 * 백엔드:
 *   POST   /api/v1/support/inquiries                  본문/타입/첨부 URL 제출
 *   POST   /api/v1/support/inquiries/image-upload     multipart 이미지 1장
 *   GET    /api/v1/support/inquiries                  본인 목록 페이지네이션
 *   GET    /api/v1/support/inquiries/{id}             본인 상세 (첨부 + 답변)
 */

import { apiFetch } from "@/lib/api-client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type InquiryType =
  | "billing"
  | "account"
  | "usage"
  | "bug"
  | "suggestion"
  | "other";

export type InquiryStatus = "open" | "in_progress" | "resolved";

export interface AttachmentRef {
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface AttachmentView {
  id: number;
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface InquiryReplyView {
  reply_id: number;
  reply_html_safe: string;
  created_at: string;
}

export interface InquiryListItem {
  id: number;
  inquiry_type: InquiryType;
  subject: string;
  status: InquiryStatus;
  created_at: string;
  resolved_at: string | null;
  has_attachments: boolean;
  reply_count: number;
}

export interface InquiryListResponse {
  items: InquiryListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface InquiryDetailResponse {
  id: number;
  inquiry_type: InquiryType;
  subject: string;
  body: string;
  status: InquiryStatus;
  created_at: string;
  resolved_at: string | null;
  attachments: AttachmentView[];
  replies: InquiryReplyView[];
}

export interface InquirySubmitArgs {
  inquiry_type: InquiryType;
  subject: string;
  body: string;
  attachments: AttachmentRef[];
}

export interface InquirySubmitResponse {
  inquiry_id: number;
}

export interface InquiryImageUploadResponse {
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export const INQUIRY_TYPE_LABELS: Record<InquiryType, string> = {
  billing: "결제·환불",
  account: "계정",
  usage: "기능 사용법",
  bug: "오류·버그",
  suggestion: "건의사항",
  other: "기타",
};

export const INQUIRY_STATUS_LABELS: Record<InquiryStatus, string> = {
  open: "접수",
  in_progress: "처리중",
  resolved: "답변완료",
};

export async function postInquiry(
  args: InquirySubmitArgs,
): Promise<InquirySubmitResponse> {
  return apiFetch<InquirySubmitResponse>("/api/v1/support/inquiries", {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export async function listMyInquiries(
  page = 1,
  perPage = 20,
): Promise<InquiryListResponse> {
  const qs = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  return apiFetch<InquiryListResponse>(
    `/api/v1/support/inquiries?${qs.toString()}`,
    { method: "GET" },
  );
}

export async function getMyInquiry(
  inquiryId: number,
): Promise<InquiryDetailResponse> {
  return apiFetch<InquiryDetailResponse>(
    `/api/v1/support/inquiries/${inquiryId}`,
    { method: "GET" },
  );
}

/** multipart 업로드 — apiFetch는 JSON 전제이므로 직접 fetch. credentials:include 유지. */
export async function uploadInquiryImage(
  file: File,
): Promise<InquiryImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE}/api/v1/support/inquiries/image-upload`,
    {
      method: "POST",
      credentials: "include",
      body: formData,
    },
  );
  if (!res.ok) {
    let message = "이미지 업로드에 실패했습니다.";
    try {
      const body = (await res.json()) as { message?: string };
      if (body?.message) message = body.message;
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }
  return (await res.json()) as InquiryImageUploadResponse;
}
