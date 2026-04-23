/**
 * Sentry 서버 설정 — Next.js 서버 사이드 에러 추적
 * PII 자동 스크러빙 활성화
 */

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT ?? "development",
  sendDefaultPii: false,

  beforeSend(event) {
    if (event.user) {
      delete event.user.email;
      delete event.user.ip_address;
    }
    return event;
  },
});
