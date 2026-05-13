// v1.0 자가 환불 큐의 reason_code — 신규 발생 경로는 모두 제거됐으나,
// 과거 audit_logs row 를 화면에 표시하기 위해 라벨 매핑만 유지한다.
type RefundReasonCode =
  | "qa_count_exceeded"
  | "period_exceeded"
  | "both"
  | "no_subscription";

const REFUND_REASON_CODE_LABELS: Record<RefundReasonCode, string> = {
  period_exceeded: "환불 가능 기간(7일) 초과",
  qa_count_exceeded: "질의 사용 발생",
  both: "기간 초과 + 질의 사용",
  no_subscription: "구독 정보 없음",
};

function formatRefundReason(code: RefundReasonCode | null): string {
  if (code === null) return "-";
  return REFUND_REASON_CODE_LABELS[code] ?? code;
}

export const FINANCE_AUDIT_ACTION_LABELS: Record<string, string> = {
  "refund.manual.approve": "환불 승인",
  "refund.manual.deny": "환불 거부",
  "subscription.extended_killswitch": "자동 구독 연장 (비상정지)",
};

export const FINANCE_AUDIT_ACTIONS: Array<{ value: string; label: string }> = [
  { value: "refund.manual.approve", label: "환불 승인" },
  { value: "refund.manual.deny", label: "환불 거부" },
  {
    value: "subscription.extended_killswitch",
    label: "자동 구독 연장 (비상정지)",
  },
];

export function formatFinanceAuditAction(action: string): string {
  return FINANCE_AUDIT_ACTION_LABELS[action] ?? action;
}

export type FinanceAuditActionTone = "approve" | "deny" | "extend" | "generic";

export function getFinanceAuditActionTone(action: string): FinanceAuditActionTone {
  if (action === "refund.manual.approve") return "approve";
  if (action === "refund.manual.deny") return "deny";
  if (action === "subscription.extended_killswitch") return "extend";
  return "generic";
}

interface ParsedFinanceAuditDiff {
  amountKrw: number | null;
  paymentId: number | null;
  reasonCode: RefundReasonCode | null;
  reasonLabel: string | null;
  noteLength: number | null;
  durationSeconds: number | null;
  extendedTo: string | null;
  killswitchStateId: number | null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function parseFinanceAuditDiff(
  action: string,
  diff: Record<string, unknown> | null,
): ParsedFinanceAuditDiff {
  const empty: ParsedFinanceAuditDiff = {
    amountKrw: null,
    paymentId: null,
    reasonCode: null,
    reasonLabel: null,
    noteLength: null,
    durationSeconds: null,
    extendedTo: null,
    killswitchStateId: null,
  };
  if (!diff) return empty;

  if (
    action === "refund.manual.approve" ||
    action === "refund.manual.deny"
  ) {
    const reasonCodeRaw = asString(diff.reason_code);
    const reasonCode = (reasonCodeRaw ?? null) as RefundReasonCode | null;
    return {
      ...empty,
      amountKrw: asNumber(diff.amount_krw),
      paymentId: asNumber(diff.payment_id),
      reasonCode,
      reasonLabel:
        reasonCode !== null ? formatRefundReason(reasonCode) : null,
      noteLength: asNumber(diff.note_length),
    };
  }

  if (action === "subscription.extended_killswitch") {
    return {
      ...empty,
      durationSeconds: asNumber(diff.duration_seconds),
      extendedTo: asString(diff.extended_to),
      killswitchStateId: asNumber(diff.killswitch_state_id),
    };
  }

  return empty;
}
