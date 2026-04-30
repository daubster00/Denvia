/** features/account 타입 정의 — Story 4.3. */

export interface UsageSummary {
  month_question_count: number;
  daily_used: number;
  daily_limit: number;
  daily_remaining: number;
  daily_reset_at: string;
  subscription_status: "free" | "pro" | "admin";
  segment: "doctor" | "hygienist" | "student_other" | null;
  years_of_experience: number | null;
  show_subscribe_button: boolean;
}
