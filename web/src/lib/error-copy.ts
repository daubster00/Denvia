/**
 * API 에러 코드 → 한국어 메시지 맵
 * 새 에러 코드는 DOMAIN_ACTION 형식으로 추가 (예: AUTH_INVALID_PASSWORD)
 */

export const errorCopy: Record<string, string> = {
  AUTH_NOT_AUTHENTICATED: "로그인이 필요합니다.",
  AUTH_SESSION_EXPIRED: "세션이 만료되었습니다. 다시 로그인해주세요.",
  AUTH_INVALID_TOKEN: "로그인이 필요합니다.",
  RATE_LIMITED: "잠시 후 다시 시도해주세요.",

  // Story 1.6 — OAuth
  OAUTH_CANCELLED: "소셜 로그인이 취소되었습니다",
  OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP:
    "이 이메일은 이메일 가입으로 등록되어 있습니다. 이메일 로그인을 이용해주세요",
  OAUTH_PHONE_COLLISION:
    "이 휴대폰은 이미 가입된 계정이 있습니다. 최초 가입 방식으로 로그인해주세요",
  OAUTH_PROVIDER_UNAVAILABLE:
    "소셜 로그인이 일시 지연됩니다. 잠시 후 다시 시도해주세요",
  OAUTH_STATE_INVALID:
    "소셜 로그인 세션이 만료되었습니다. 다시 시도해주세요",
  OAUTH_PENDING_EXPIRED:
    "소셜 가입 세션이 만료되었습니다. 다시 시도해주세요",
  OAUTH_PENDING_INVALID:
    "소셜 가입 세션이 만료되었습니다. 다시 시도해주세요",
  OAUTH_PROVIDER_UNKNOWN: "지원하지 않는 소셜 로그인입니다",
  SMS_TOKEN_INVALID: "휴대폰 인증이 필요합니다",
};

export function getErrorMessage(code: string): string {
  // hasOwn 가드로 prototype pollution(`__proto__`·`toString` 등) 및 빈 코드 방어
  if (!code || !Object.prototype.hasOwnProperty.call(errorCopy, code)) {
    return "알 수 없는 오류가 발생했습니다.";
  }
  return errorCopy[code];
}
