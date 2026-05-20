/**
 * 마이페이지 회원정보 API 클라이언트.
 *
 * 백엔드 엔드포인트:
 *   GET    /api/v1/me/profile
 *   PATCH  /api/v1/me/profile
 *   POST   /api/v1/me/password         (소셜 회원 초기 설정 / 임시PW 교체)
 *   POST   /api/v1/me/password/change  (기존 비밀번호 확인 후 변경)
 */

import { apiFetch } from "@/lib/api-client";

export type Gender = "male" | "female";

export type Segment = "doctor" | "hygienist" | "student_other";

export interface ProfileResponse {
  email: string;
  name: string | null;
  phone: string | null;
  phone_verified: boolean;
  is_social: boolean;
  postcode: string | null;
  address_road: string | null;
  address_detail: string | null;
  gender: Gender | null;
  birthdate: string | null; // ISO date "YYYY-MM-DD"
  marketing_consent: boolean;
  marketing_consent_at: string | null; // ISO 8601
  // 가입유형/연차 — 읽기 전용 표시. 변경은 관리자만(AR34).
  segment: Segment | null;
  years_of_experience: number | null;
}

export interface ProfileUpdatePayload {
  name?: string | null;
  phone?: string | null;
  phone_verification_token?: string | null;
  postcode?: string | null;
  address_road?: string | null;
  address_detail?: string | null;
  gender?: Gender | null;
  birthdate?: string | null; // "YYYY-MM-DD" 또는 null
  marketing_consent?: boolean;
}

export async function fetchProfile(): Promise<ProfileResponse> {
  return apiFetch<ProfileResponse>("/api/v1/me/profile");
}

export async function updateProfile(payload: ProfileUpdatePayload): Promise<void> {
  await apiFetch<void>("/api/v1/me/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** 소셜 회원 초기 비밀번호 설정 (또는 임시PW 교체) — 기존 비밀번호 확인 없음. */
export async function setInitialPassword(new_password: string): Promise<void> {
  await apiFetch<{ ok: boolean }>("/api/v1/me/password", {
    method: "POST",
    body: JSON.stringify({ new_password }),
  });
}

/** 정규 비밀번호 변경 — 기존 비밀번호 확인 필수. */
export async function changePasswordWithCurrent(payload: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await apiFetch<{ ok: boolean }>("/api/v1/me/password/change", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
