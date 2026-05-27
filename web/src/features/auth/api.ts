import { apiFetch } from "@/lib/api-client";
import type { SessionUser } from "@/types/api";

/** find-id / 소셜 가입 경로 식별 — 서버 signup_method 응답 타입. */
export type SignupMethod = "email" | "kakao" | "google" | "naver" | "social";

/** 현재 세션 사용자 정보 조회 */
export async function fetchMe(): Promise<SessionUser> {
  return apiFetch<SessionUser>("/api/v1/me");
}

/** SMS OTP 발송 */
export interface SmsSendResult {
  sent_at: string;
  cooldown_seconds: number;
  max_retries: number;
  debug_code?: string | null;
}

export async function sendSmsOtp(phone: string, purpose: "signup" | "find_id" | "find_password" | "phone_change") {
  return apiFetch<SmsSendResult>(
    "/api/v1/auth/sms/send",
    { method: "POST", body: JSON.stringify({ phone, purpose }) }
  );
}

/** SMS OTP 검증 */
export async function verifySmsOtp(phone: string, code: string, purpose: "signup" | "find_id" | "find_password" | "phone_change") {
  return apiFetch<{ phone_verification_token: string }>(
    "/api/v1/auth/sms/verify",
    { method: "POST", body: JSON.stringify({ phone, code, purpose }) }
  );
}

/** 회원가입 */
export async function signup(payload: {
  email: string;
  password: string;
  phone: string;
  phone_verification_token: string;
  /** 선택 입력 — null이면 미입력. 백엔드에서 빈문자는 null로 정규화. */
  name?: string | null;
  birthdate?: string | null; // "YYYY-MM-DD"
  gender?: "male" | "female" | null;
  postcode?: string | null;
  address_road?: string | null;
  address_detail?: string | null;
}) {
  return apiFetch<SessionUser>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 가입유형 설정 */
export async function setSegment(payload: {
  segment: "doctor" | "hygienist" | "student_other";
  years_of_experience?: number;
}) {
  return apiFetch<void>("/api/v1/me/segment", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 이메일 로그인 */
export async function login(payload: {
  email: string;
  password: string;
  persist_session: boolean;
}) {
  return apiFetch<import("@/types/api").SessionUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 로그아웃 */
export async function logout() {
  return apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
}

/** 비밀번호 찾기 — SMS 임시 비밀번호 발송.
 *
 * 소셜 전용 계정인 경우 SMS 대신 `linked_providers`에 연결된 provider 목록이 담겨 온다.
 * 그 외(일반 가입·미일치·오류)는 모두 `linked_providers: []` — 계정 열거 방지 유지.
 */
export type FindPasswordProvider = "kakao" | "google" | "naver";

export async function requestPasswordReset(payload: { email: string; phone: string }) {
  return apiFetch<{ ok: boolean; linked_providers: FindPasswordProvider[] }>(
    "/api/v1/auth/find-password",
    { method: "POST", body: JSON.stringify(payload) },
  );
}

/** 아이디(이메일) 찾기 — phone_verification_token으로 마스킹된 이메일 반환 */
export async function lookupId(payload: { phone_verification_token: string }) {
  return apiFetch<{
    email_masked: string | null;
    signup_method: SignupMethod | null;
  }>(
    "/api/v1/auth/find-id",
    { method: "POST", body: JSON.stringify(payload) }
  );
}

/** OAuth 신규 가입 SMS 보충 완료 (Story 1.6) */
export async function completeOAuthSignup(payload: {
  signup_pending_token: string;
  phone: string;
  phone_verification_token: string;
}) {
  return apiFetch<{
    user_id: number;
    email: string;
    role: string;
    subscription_status: string;
  }>("/api/v1/auth/oauth/complete", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 임시 비밀번호 → 신규 비밀번호 변경 */
export async function changePassword(payload: { new_password: string }) {
  return apiFetch<{ ok: boolean }>("/api/v1/me/password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Story 1.7: 회원 탈퇴 ─────────────────────────────────────────────────────

/** 소셜 가입자 탈퇴용 SMS OTP 발송 — 마스킹된 휴대폰을 응답에 포함. */
export async function sendWithdrawOtp(): Promise<{ masked_phone: string }> {
  return apiFetch<{ masked_phone: string }>("/api/v1/me/withdraw/send-otp", {
    method: "POST",
  });
}

/** 소셜 가입자 탈퇴용 SMS OTP 검증 — phone_verification_token 발급. */
export async function verifyWithdrawOtp(code: string) {
  return apiFetch<{ phone_verification_token: string }>(
    "/api/v1/me/withdraw/verify-otp",
    { method: "POST", body: JSON.stringify({ code }) }
  );
}

/** 본인 계정 탈퇴 — 자체 가입자는 password, 소셜 가입자는 phone_verification_token. */
export async function withdraw(payload: {
  password?: string;
  phone_verification_token?: string;
}): Promise<void> {
  await apiFetch<void>("/api/v1/me", {
    method: "DELETE",
    body: JSON.stringify(payload),
  });
}
