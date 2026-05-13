/** Admin 고객문의 + 환불 — 한국어 라벨. */

import type {
  InquiryStatus,
  InquiryType,
  UserSegment,
} from "@/features/admin-support/api/inquiries";
import type {
  RefundQueueStatus,
  RefundReasonCode,
} from "@/features/admin-support/api/refunds";

export const INQUIRY_STATUS_LABELS: Record<InquiryStatus, string> = {
  open: "신규",
  in_progress: "처리중",
  resolved: "완료",
};

export function formatInquiryStatus(status: InquiryStatus): string {
  return INQUIRY_STATUS_LABELS[status] ?? status;
}

export const INQUIRY_TYPE_LABELS: Record<InquiryType, string> = {
  billing: "결제·환불",
  account: "계정",
  usage: "기능 사용법",
  bug: "오류·버그",
  suggestion: "건의사항",
  other: "기타",
};

export function formatInquiryType(type: InquiryType): string {
  return INQUIRY_TYPE_LABELS[type] ?? type;
}

export const SEGMENT_LABELS: Record<UserSegment, string> = {
  doctor: "치과의사",
  hygienist: "치위생사",
  student_other: "학생/기타",
};

export function formatSegment(segment: UserSegment | null): string {
  if (segment === null) return "-";
  return SEGMENT_LABELS[segment] ?? segment;
}

export const REFUND_QUEUE_STATUS_LABELS: Record<RefundQueueStatus, string> = {
  pending: "대기",
  approved: "승인됨",
  denied: "거부됨",
};

export const REFUND_REASON_CODE_LABELS: Record<RefundReasonCode, string> = {
  period_exceeded: "환불 가능 기간(7일) 초과",
  qa_count_exceeded: "질의 사용 발생",
  both: "기간 초과 + 질의 사용",
  no_subscription: "구독 정보 없음",
};

export function formatRefundReason(code: RefundReasonCode | null): string {
  if (code === null) return "-";
  return REFUND_REASON_CODE_LABELS[code] ?? code;
}
