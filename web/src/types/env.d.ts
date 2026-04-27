/** NEXT_PUBLIC_* 환경변수 타입 선언 */

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_API_URL?: string;
    NEXT_PUBLIC_SENTRY_DSN?: string;
    /** Story 2.7 — 우측 하단 고객문의 FAB 클릭 시 새 탭으로 열리는 카카오톡 채널 URL. 미설정 시 위젯 비렌더. */
    NEXT_PUBLIC_KAKAO_CHANNEL_URL?: string;
  }
}
