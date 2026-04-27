"use client";

export function AdvisoryChip() {
  return (
    <p
      role="note"
      aria-label="이 답변은 임상 참고용입니다"
      style={{
        display: "inline-block",
        padding: "4px 10px",
        backgroundColor: "#F7F7F8",
        border: "1px solid #E1E2E4",
        borderRadius: 20,
        fontSize: 12,
        color: "#70737C",
        margin: 0,
        lineHeight: 1.4,
      }}
    >
      임상 참고용 답변 · 전문가 판단 우선
    </p>
  );
}
