/**
 * Sentry 클라이언트 설정 — 브라우저 사이드 에러 추적
 * PII 자동 스크러빙 활성화 (이메일·휴대폰 마스킹)
 */

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT ?? "development",
  sendDefaultPii: false,

  beforeSend(event) {
    // PII 필드 스크러빙
    if (event.user) {
      delete event.user.email;
      delete event.user.ip_address;
    }
    return event;
  },
});
