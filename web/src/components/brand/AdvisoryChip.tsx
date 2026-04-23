"use client";

/**
 * 면책 고지 칩 — 하단 상시 표시 (NFR-C6).
 * "본 답변은 참고용이며 의학적 판단은 전문가 책임"
 */
export function AdvisoryChip() {
  return (
    <p
      role="note"
      style={{
        display: "inline-block",
        padding: "6px 12px",
        backgroundColor: "#F7F7F8",
        border: "1px solid #E1E2E4",
        borderRadius: 20,
        fontSize: 13,
        color: "#5A5C63",
        margin: 0,
        lineHeight: 1.4,
      }}
    >
      본 답변은 참고용이며 의학적 판단은 전문가 책임
    </p>
  );
}
