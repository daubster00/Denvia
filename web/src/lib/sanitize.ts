"use client";

/** isomorphic-dompurify 클라이언트 sanitize — Story 4.5 AC-13.
 *
 * 서버 nh3 sanitize에 더해 클라이언트에서도 한 번 더 sanitize하여
 * XSS 이중 방어. ALLOWED_URI_REGEXP는 https?:// 만 허용 — mailto:는
 * 의도적으로 차단(이메일 0건 정책 일관, memory project_email_zero_policy).
 */

import DOMPurify from "isomorphic-dompurify";

const PROFILE_INBOX = {
  ALLOWED_TAGS: [
    "b",
    "strong",
    "i",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "p",
    "br",
  ],
  ALLOWED_ATTR: ["href", "src", "alt", "target", "rel"],
  ALLOWED_URI_REGEXP: /^https?:\/\//i,
} as const;

export function sanitizeNoticeHtml(html: string): string {
  return DOMPurify.sanitize(html, PROFILE_INBOX) as unknown as string;
}
