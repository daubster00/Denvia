"use client";

/** 접근성 Skip link — 포커스 시 표시, #main으로 이동 (WCAG 2.4.1, UX-DR24) */
export function SkipLink() {
  return (
    <a
      href="#main"
      style={{
        position: "fixed",
        top: -100,
        left: 8,
        zIndex: 9999,
        padding: "8px 16px",
        backgroundColor: "#7C3AED",
        color: "#fff",
        borderRadius: 4,
        fontSize: 14,
        fontWeight: 600,
        textDecoration: "none",
        transition: "top 0.1s",
      }}
      onFocus={(e) => { (e.currentTarget as HTMLAnchorElement).style.top = "8px"; }}
      onBlur={(e) => { (e.currentTarget as HTMLAnchorElement).style.top = "-100px"; }}
    >
      메인 콘텐츠로 건너뛰기
    </a>
  );
}
