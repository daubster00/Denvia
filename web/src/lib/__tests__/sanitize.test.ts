import { describe, it, expect } from "vitest";
import { normalizeCssColorToHex, sanitizeNoticeHtml } from "../sanitize";

describe("normalizeCssColorToHex", () => {
  it("소문자 hex는 그대로 통과한다", () => {
    expect(normalizeCssColorToHex("#dc2626")).toBe("#dc2626");
  });

  it("대문자 hex는 소문자로 정규화한다", () => {
    expect(normalizeCssColorToHex("#DC2626")).toBe("#dc2626");
  });

  it("rgb(R, G, B) 표기를 소문자 hex로 변환한다 (수정요청 #119)", () => {
    expect(normalizeCssColorToHex("rgb(220, 38, 38)")).toBe("#dc2626");
  });

  it("공백 없는 rgb 표기도 변환한다", () => {
    expect(normalizeCssColorToHex("rgb(37,99,235)")).toBe("#2563eb");
  });

  it("alpha=1인 rgba 표기를 hex로 변환한다", () => {
    expect(normalizeCssColorToHex("rgba(220, 38, 38, 1)")).toBe("#dc2626");
  });

  it("alpha가 1이 아닌 rgba는 null을 반환한다", () => {
    expect(normalizeCssColorToHex("rgba(220, 38, 38, 0.5)")).toBeNull();
  });

  it("255 초과 채널 값은 null을 반환한다", () => {
    expect(normalizeCssColorToHex("rgb(300, 0, 0)")).toBeNull();
  });

  it("인식 불가 형식(named color 등)은 null을 반환한다", () => {
    expect(normalizeCssColorToHex("red")).toBeNull();
    expect(normalizeCssColorToHex("#fff")).toBeNull();
    expect(normalizeCssColorToHex("")).toBeNull();
  });
});

describe("sanitizeNoticeHtml — span 색상 필터", () => {
  it("프리셋 hex 색은 유지한다", () => {
    const out = sanitizeNoticeHtml('<span style="color: #dc2626">빨강</span>');
    expect(out).toContain("color: #dc2626");
    expect(out).toContain("빨강");
  });

  it("rgb 형식 프리셋 색을 hex로 정규화해 유지한다 (수정요청 #119)", () => {
    const out = sanitizeNoticeHtml(
      '<span style="color: rgb(220, 38, 38)">빨강</span>',
    );
    expect(out).toContain("color: #dc2626");
  });

  it("rgb 형식 비프리셋 색은 style 자체를 제거한다", () => {
    const out = sanitizeNoticeHtml(
      '<span style="color: rgb(1, 2, 3)">임의색</span>',
    );
    expect(out).not.toContain("style");
    expect(out).toContain("임의색");
  });

  it("rgb 색 + 프리셋 font-size 조합은 둘 다 유지한다", () => {
    const out = sanitizeNoticeHtml(
      '<span style="color: rgb(22, 163, 74); font-size: 20px">본문</span>',
    );
    expect(out).toContain("color: #16a34a");
    expect(out).toContain("font-size: 20px");
  });

  it("script 태그는 제거한다", () => {
    const out = sanitizeNoticeHtml("<p>안녕</p><script>alert(1)</script>");
    expect(out).not.toContain("script");
    expect(out).toContain("안녕");
  });
});
