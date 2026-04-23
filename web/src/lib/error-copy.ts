/**
 * API 에러 코드 → 한국어 메시지 맵
 * 새 에러 코드는 DOMAIN_ACTION 형식으로 추가 (예: AUTH_INVALID_PASSWORD)
 */

export const errorCopy: Record<string, string> = {
  AUTH_NOT_AUTHENTICATED: "로그인이 필요합니다.",
  AUTH_SESSION_EXPIRED: "세션이 만료되었습니다. 다시 로그인해주세요.",
  AUTH_INVALID_TOKEN: "로그인이 필요합니다.",
  RATE_LIMITED: "잠시 후 다시 시도해주세요.",
};

export function getErrorMessage(code: string): string {
  return errorCopy[code] ?? "알 수 없는 오류가 발생했습니다.";
}
