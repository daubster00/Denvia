/** NEXT_PUBLIC_* 환경변수 타입 선언 */

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_API_URL?: string;
    NEXT_PUBLIC_SENTRY_DSN?: string;
  }
}
