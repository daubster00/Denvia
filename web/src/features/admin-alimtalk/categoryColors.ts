/**
 * Story 4.6 — 알림톡 카테고리 칩 색상 매핑.
 *
 * Story 10.4 `action-groups.ts` 패턴 답습. 인라인 색상 금지(NFR feedback_no_inline_css)
 * — CSS Modules 의 attribute selector 가 본 매핑을 참조한다.
 */

import type { AlimtalkCategory } from "./api";

export const CATEGORY_LABELS: Record<AlimtalkCategory, string> = {
  billing: "결제",
  subscription: "구독",
  system: "시스템",
  support: "고객문의",
  sms: "SMS",
};

// 공지(notice) 카테고리는 발송 폐기로 카탈로그에서 제외 — 색상도 정의하지 않는다.
export const CATEGORY_COLORS: Record<AlimtalkCategory, string> = {
  billing: "#7c3aed", // 보라
  subscription: "#0891b2", // 청록
  support: "#ea580c", // 주황
  system: "#6b7280", // 회색
  sms: "#0d9488", // 짙은 청록 (SMS 채널)
};

export function labelForCategory(category: AlimtalkCategory): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function colorForCategory(category: AlimtalkCategory): string {
  return CATEGORY_COLORS[category] ?? "#9ca3af";
}
