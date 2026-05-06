/** API 공용 타입 정의 — snake_case 단일 정책 (camelCase 변환 금지) */

export interface FeedbackCreateRequest {
  qa_log_id: number;
  rating: "good" | "bad";
}

export interface FeedbackResponse {
  qa_log_id: number;
  rating: "good" | "bad";
  change_count: number;
  action: "created" | "updated" | "unchanged";
}

export interface QuotaResponse {
  subscription_status: "free" | "pro" | "blocked" | "admin";
  daily_limit: number;
  used_today: number;
  remaining: number;
  reset_at: string;
  show_upgrade_prompt: boolean;
  show_subscribe_button: boolean;
  delay_seconds: number;
}

export interface SessionUser {
  user_id: number;
  email: string;
  role: "user" | "admin";
  subscription_status: "free" | "pro" | "blocked";
  segment: "doctor" | "hygienist" | "student_other" | null;
  years_of_experience: number | null;
  must_reset_password: boolean;
  /** Story 1.7: 소셜 전용 가입 여부(서버의 password_hash IS NULL). */
  is_social: boolean;
}

export class ApiError extends Error {
  code: string;
  trace_id: string;
  details?: Record<string, unknown>;

  constructor(payload: { code: string; message: string; trace_id: string; details?: Record<string, unknown> }) {
    super(payload.message);
    this.code = payload.code;
    this.trace_id = payload.trace_id;
    this.details = payload.details;
  }
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  per_page: number;
  total: number;
}
