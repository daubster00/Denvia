import { describe, expect, it } from "vitest";
import {
  formatInquiryStatus,
  formatInquiryType,
  formatSegment,
  INQUIRY_TYPE_LABELS,
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
});
