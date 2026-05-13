import { describe, expect, it } from "vitest";
import {
  formatInquiryStatus,
  formatInquiryType,
  formatRefundReason,
  formatSegment,
  INQUIRY_TYPE_LABELS,
  REFUND_QUEUE_STATUS_LABELS,
  REFUND_REASON_CODE_LABELS,
} from "../labels";

describe("labels (Story 9.3)", () => {
  it("formats inquiry status to Korean labels", () => {
    expect(formatInquiryStatus("open")).toBe("신규");
    expect(formatInquiryStatus("in_progress")).toBe("처리중");
    expect(formatInquiryStatus("resolved")).toBe("완료");
  });

  it("formats inquiry type to Korean labels", () => {
    expect(formatInquiryType("billing")).toBe("결제·환불");
    expect(formatInquiryType("account")).toBe("계정");
    expect(formatInquiryType("usage")).toBe("기능 사용법");
    expect(formatInquiryType("bug")).toBe("오류·버그");
    expect(formatInquiryType("suggestion")).toBe("건의사항");
    expect(formatInquiryType("other")).toBe("기타");
    expect(Object.keys(INQUIRY_TYPE_LABELS).sort()).toEqual([
      "account",
      "billing",
      "bug",
      "other",
      "suggestion",
      "usage",
    ]);
  });

  it("formats segment to Korean labels", () => {
    expect(formatSegment("doctor")).toBe("치과의사");
    expect(formatSegment("hygienist")).toBe("치위생사");
    expect(formatSegment("student_other")).toBe("학생/기타");
    expect(formatSegment(null)).toBe("-");
  });

  it("formats refund reason code to Korean labels", () => {
    expect(formatRefundReason("period_exceeded")).toBe("환불 가능 기간(7일) 초과");
    expect(formatRefundReason("qa_count_exceeded")).toBe("질의 사용 발생");
    expect(formatRefundReason("both")).toBe("기간 초과 + 질의 사용");
    expect(formatRefundReason("no_subscription")).toBe("구독 정보 없음");
    expect(formatRefundReason(null)).toBe("-");
  });

  it("provides refund queue status labels", () => {
    expect(REFUND_QUEUE_STATUS_LABELS.pending).toBe("대기");
    expect(REFUND_QUEUE_STATUS_LABELS.approved).toBe("승인됨");
    expect(REFUND_QUEUE_STATUS_LABELS.denied).toBe("거부됨");
  });

  it("exposes the full reason code label map", () => {
    expect(Object.keys(REFUND_REASON_CODE_LABELS).sort()).toEqual([
      "both",
      "no_subscription",
      "period_exceeded",
      "qa_count_exceeded",
    ]);
  });
});
