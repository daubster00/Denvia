/**
 * Denvia 브랜드 토큰 — WDS semantic 토큰 오버라이드용 CSS 변수.
 * WDS ThemeProvider 위에 <Global> 로 겹쳐 바이올렛/핑크 팔레트를 적용한다.
 * --brand-gradient는 WDS 범위 외 커스텀 토큰 (globals.css 관리).
 */

export const denviaTokenOverrides = `
  :root {
    --semantic-primary-normal: #8B5CF6;
    --semantic-primary-normal-rgb: 139, 92, 246;
    --semantic-primary-strong: #7C3AED;
    --semantic-primary-strong-rgb: 124, 58, 237;
    --semantic-primary-heavy: #6D28D9;
    --semantic-primary-heavy-rgb: 109, 40, 217;
  }
` as const;

/** 브랜드 그라디언트 — CTA 버튼/배경용 */
export const brandGradient = "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)";

/** primary-600 solid fallback — 그라디언트 대비 미달 시 사용 (UX Spec §1601) */
export const primarySolid = "#7C3AED";
