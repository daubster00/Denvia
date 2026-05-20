/**
 * Story 6.1 — 한국어 라벨 매핑 (백엔드 enum → 사용자 표시).
 */

import type {
  Segment,
  SubscriptionStatus,
} from "@/features/admin-users/api/users";

export const SEGMENT_LABELS: Record<Segment, string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

export const SUBSCRIPTION_STATUS_LABELS: Record<SubscriptionStatus, string> = {
  free: "무료",
  pro: "Pro",
  blocked: "차단",
};

export const ANOMALY_TYPE_LABELS: Record<string, string> = {
  login_brute_force: "로그인 무차별 시도",
  rapid_questions: "빠른 연속 질의",
  concurrent_ip_login: "복수 IP 동시 로그인",
  repeated_question: "반복 질의",
  recovery_abuse: "계정 복구 남용",
};

export function formatSegment(segment: Segment | null): string {
  if (!segment) return "—";
  return SEGMENT_LABELS[segment] ?? segment;
}

export function formatSubscriptionStatus(status: SubscriptionStatus): string {
  return SUBSCRIPTION_STATUS_LABELS[status] ?? status;
}

export function formatAnomalyType(type: string): string {
  return ANOMALY_TYPE_LABELS[type] ?? type;
}

// Story 6.2 — 감사 로그 액션 한국어 라벨
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  "user.permission_edit": "권한 수정",
  "user.speed_override": "응답 속도 변경",
  "user.block_auto_expired": "차단 자동 만료",
};

export function formatAuditAction(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action;
}

// Story 6.2 — 감사 로그 diff 필드 한국어 라벨
export const DIFF_FIELD_LABELS: Record<string, string> = {
  subscription_status: "구독 상태",
  segment: "가입유형",
  is_blocked: "차단 여부",
  blocked_until: "차단 만료",
  daily_quota_override: "1일 한도",
  block_reason: "차단 사유",
  pro_granted_by_admin: "관리자 부여 Pro",
};

export function formatDiffField(field: string): string {
  return DIFF_FIELD_LABELS[field] ?? field;
}

export function formatDiffValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (field === "subscription_status" && typeof value === "string") {
    const known = SUBSCRIPTION_STATUS_LABELS[value as SubscriptionStatus];
    return known ?? value;
  }
  if (field === "segment" && typeof value === "string") {
    const known = SEGMENT_LABELS[value as Segment];
    return known ?? value;
  }
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") {
    // ISO datetime → KST
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      try {
        return new Intl.DateTimeFormat("ko-KR", {
          timeZone: "Asia/Seoul",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }).format(new Date(value));
      } catch {
        return value;
      }
    }
    return value;
  }
  return JSON.stringify(value);
}
