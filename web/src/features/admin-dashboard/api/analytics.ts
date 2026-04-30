const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface UserTokensRow {
  user_id: number;
  email: string;
  segment: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: string;
  question_count: number;
  avg_cost_per_question: string;
}

export interface UserTokensListResponse {
  items: UserTokensRow[];
  page: number;
  per_page: number;
  total: number;
  range: string;
  year_month: string | null;
}

export interface FetchUserTokensParams {
  range?: "day" | "month" | "year";
  year_month?: string;
  from?: string;
  to?: string;
  page?: number;
  per_page?: number;
}

export async function fetchUserTokens(
  params: FetchUserTokensParams = {}
): Promise<UserTokensListResponse> {
  const query = new URLSearchParams();
  if (params.range) query.set("range", params.range);
  if (params.year_month) query.set("year_month", params.year_month);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));

  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/user-tokens?${query.toString()}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`user-tokens fetch failed: ${res.status}`);
  return res.json() as Promise<UserTokensListResponse>;
}

// ---------------------------------------------------------------------------
// Story 5.3: 가입자 추세 / 구독 분포
// ---------------------------------------------------------------------------

export type SignupsUnit = "day" | "week" | "month" | "year";

export interface SignupsBucket {
  bucket_start: string; // YYYY-MM-DD (KST)
  cumulative: number;
  active: number;
  withdrawn: number;
}

export interface SignupsResponse {
  unit: SignupsUnit;
  from: string;
  to: string;
  buckets: SignupsBucket[];
}

export interface FetchSignupsParams {
  unit?: SignupsUnit;
  from?: string;
  to?: string;
}

export async function fetchSignups(
  params: FetchSignupsParams = {}
): Promise<SignupsResponse> {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/signups${qs ? `?${qs}` : ""}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`signups fetch failed: ${res.status}`);
  return res.json() as Promise<SignupsResponse>;
}

export interface UpcomingRenewal {
  user_id: number;
  email_masked: string;
  next_charge_at: string;
  amount_krw: number;
}

export interface SubscribersResponse {
  as_of: string;
  free_count: number;
  pro_count: number;
  blocked_count: number;
  withdrawn_count: number;
  pending_cancellation_count: number | null;
  upcoming_renewals: UpcomingRenewal[];
}

export async function fetchSubscribers(): Promise<SubscribersResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/subscribers?as_of=now`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`subscribers fetch failed: ${res.status}`);
  return res.json() as Promise<SubscribersResponse>;
}

// ---------------------------------------------------------------------------
// Story 5.4: 피드백 분석
// ---------------------------------------------------------------------------

export interface FeedbackSummary {
  good_count: number;
  bad_count: number;
  good_ratio: number | null;
}

export interface FeedbackSeriesItem {
  bucket_start: string;
  good: number;
  bad: number;
}

export interface FeedbackItem {
  qa_log_id: number;
  question_text: string;
  answer_text: string | null;
  rating: "good" | "bad";
  segment: string | null;
  created_at: string;
}

export interface FeedbackResponse {
  unit: string;
  from: string;
  to: string;
  rating_filter: string;
  summary: FeedbackSummary;
  series: FeedbackSeriesItem[];
  items: FeedbackItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchFeedbackParams {
  unit?: "day" | "week" | "month";
  from?: string;
  to?: string;
  rating_filter?: "good" | "bad" | "all";
  page?: number;
  per_page?: number;
  q?: string;
}

export async function fetchFeedback(
  params: FetchFeedbackParams = {}
): Promise<FeedbackResponse> {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.rating_filter) query.set("rating_filter", params.rating_filter);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));
  if (params.q) query.set("q", params.q);
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/feedback?${query.toString()}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`feedback fetch failed: ${res.status}`);
  return res.json() as Promise<FeedbackResponse>;
}

export async function fetchFeedbackExport(
  params: Omit<FetchFeedbackParams, "page" | "per_page">
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(buildFeedbackExportUrl(params), {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`feedback export failed: ${res.status}`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await res.blob(),
    filename: match?.[1] ?? `feedback_${params.from || "all"}_${params.to || "all"}.xlsx`,
  };
}

export function buildFeedbackExportUrl(
  params: Omit<FetchFeedbackParams, "page" | "per_page">
): string {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.rating_filter) query.set("rating_filter", params.rating_filter);
  if (params.q) query.set("q", params.q);
  const qs = query.toString();
  return `${API_BASE}/api/v1/admin/analytics/feedback/export${qs ? `?${qs}` : ""}`;
}
