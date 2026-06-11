const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface UserTokensRow {
  user_id: number;
  email: string;
  segment: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: string;
  // 전체 시스템 KRW 통일 — 응답 시점 환율로 환산된 보조 필드.
  total_cost_krw: number;
  avg_cost_per_question_krw: number;
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
  usd_to_krw: number;
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
  new_signups: number;
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

export interface PendingCancellation {
  user_id: number;
  email_masked: string;
  canceled_at: string;          // ISO-8601
  current_period_end: string;   // ISO-8601
}

export interface SubscribersResponse {
  as_of: string;
  free_count: number;
  pro_count: number;
  blocked_count: number;
  withdrawn_count: number;
  pending_cancellation_count: number;
  pending_cancellations: PendingCancellation[];
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
// 접속 통계 — 일/주/월/년 접속자 수 + 접속횟수
// ---------------------------------------------------------------------------

export type AccessUnit = "day" | "week" | "month" | "year";

export interface AccessBucket {
  bucket_start: string; // YYYY-MM-DD (KST)
  visitors: number;     // 고유 접속자 수
  visits: number;       // 접속 횟수
}

export interface AccessResponse {
  unit: AccessUnit;
  from: string;
  to: string;
  total_visitors: number;
  total_visits: number;
  buckets: AccessBucket[];
}

export interface FetchAccessParams {
  unit?: AccessUnit;
  from?: string;
  to?: string;
}

export async function fetchAccess(
  params: FetchAccessParams = {}
): Promise<AccessResponse> {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/access${qs ? `?${qs}` : ""}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`access fetch failed: ${res.status}`);
  return res.json() as Promise<AccessResponse>;
}

// ---------------------------------------------------------------------------
// Story 5.4: 피드백 분석
// ---------------------------------------------------------------------------

export interface FeedbackSummary {
  good_count: number;
  bad_count: number;
  reviewed_count: number;
  good_ratio: number | null;
}

export interface FeedbackSeriesItem {
  bucket_start: string;
  good: number;
  bad: number;
  reviewed: number;
}

export interface FeedbackItem {
  qa_log_id: number;
  question_text: string;
  answer_text: string | null;
  rating: "good" | "bad";
  segment: string | null;
  user_id: number | null;
  email: string | null;
  created_at: string;
  reviewed_at: string | null;
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
  rating_filter?: "good" | "bad" | "reviewed" | "all";
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

export interface FeedbackRetrievedDoc {
  page_content: string;
  metadata: Record<string, unknown>;
}

export interface FeedbackDetail {
  qa_log_id: number;
  question_text: string;
  normalized_query: string | null;
  retrieved_docs: FeedbackRetrievedDoc[];
  /**
   * LLM 에 실제로 들어간 최종 프롬프트 (템플릿 + 질문 + top-k 컨텍스트 치환 완료).
   * 룰 경로 / 0062 마이그레이션 이전 행 / 스트림 중단 행은 null.
   */
  prompt_text: string | null;
  answer_text: string | null;
  rule_matched: boolean;
  status: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  latency_ms: number | null;
  created_at: string;
}

export async function fetchFeedbackDetail(
  qaLogId: number
): Promise<FeedbackDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/feedback/${qaLogId}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`feedback detail fetch failed: ${res.status}`);
  return res.json() as Promise<FeedbackDetail>;
}

export interface FeedbackReviewResponse {
  qa_log_id: number;
  reviewed: boolean;
  reviewed_at: string | null;
  reviewed_by_user_id: number | null;
}

export async function setFeedbackReviewed(
  qaLogId: number,
  reviewed: boolean
): Promise<FeedbackReviewResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/feedback/${qaLogId}/review`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed }),
    }
  );
  if (!res.ok)
    throw new Error(`feedback review toggle failed: ${res.status}`);
  return res.json() as Promise<FeedbackReviewResponse>;
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

// ---------------------------------------------------------------------------
// 질문 분석 — qa_logs 기반 일/주/월/년 합산 + 정렬·페이지 + 엑셀
// ---------------------------------------------------------------------------

export type QuestionsUnit = "day" | "week" | "month" | "year";
export type QuestionsSort = "latest" | "tokens" | "email";

export interface QuestionsBucket {
  bucket_start: string; // YYYY-MM-DD (KST)
  count: number;
}

export interface QuestionsItem {
  qa_log_id: number;
  question_text: string;
  answer_text: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: string | null;
  status: string | null;
  user_id: number | null;
  email: string | null;
  segment: string | null;
  created_at: string;
}

export interface QuestionsResponse {
  unit: QuestionsUnit;
  sort: QuestionsSort;
  from: string;
  to: string;
  total_count: number;
  buckets: QuestionsBucket[];
  items: QuestionsItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchQuestionsParams {
  unit?: QuestionsUnit;
  sort?: QuestionsSort;
  from?: string;
  to?: string;
  page?: number;
  per_page?: number;
  q?: string;
}

export async function fetchQuestions(
  params: FetchQuestionsParams = {}
): Promise<QuestionsResponse> {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.sort) query.set("sort", params.sort);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));
  if (params.q) query.set("q", params.q);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/questions${qs ? `?${qs}` : ""}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error(`questions fetch failed: ${res.status}`);
  return res.json() as Promise<QuestionsResponse>;
}

export function buildQuestionsExportUrl(
  params: Omit<FetchQuestionsParams, "page" | "per_page">
): string {
  const query = new URLSearchParams();
  if (params.unit) query.set("unit", params.unit);
  if (params.sort) query.set("sort", params.sort);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.q) query.set("q", params.q);
  const qs = query.toString();
  return `${API_BASE}/api/v1/admin/analytics/questions/export${qs ? `?${qs}` : ""}`;
}

export async function fetchQuestionsExport(
  params: Omit<FetchQuestionsParams, "page" | "per_page">
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(buildQuestionsExportUrl(params), {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`questions export failed: ${res.status}`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await res.blob(),
    filename:
      match?.[1] ??
      `questions_${params.from || "all"}_${params.to || "all"}.xlsx`,
  };
}

// ---------------------------------------------------------------------------
// Story 6.4 — 가입유형 통계
// ---------------------------------------------------------------------------

export type SegmentKey = "doctor" | "hygienist" | "student_other";
export type YearsBucket = "0-2" | "3-5" | "6-10" | "11-20" | "20+";

export interface SegmentRow {
  segment: SegmentKey;
  count: number;
  active_count: number;
  pro_count: number;
}

export interface ExperienceRow {
  segment: "doctor" | "hygienist";
  years_bucket: YearsBucket;
  count: number;
}

export interface SegmentsResponse {
  as_of: string;
  applied_filters: { include_withdrawn: boolean; include_blocked: boolean };
  total: number;
  by_segment: SegmentRow[];
  by_experience: ExperienceRow[];
}

export interface FetchSegmentsParams {
  include_withdrawn?: boolean;
  include_blocked?: boolean;
}

export async function fetchSegments(
  params: FetchSegmentsParams = {},
): Promise<SegmentsResponse> {
  const query = new URLSearchParams();
  if (params.include_withdrawn) query.set("include_withdrawn", "true");
  if (params.include_blocked) query.set("include_blocked", "true");
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/segments${qs ? `?${qs}` : ""}`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error(`segments fetch failed: ${res.status}`);
  return res.json() as Promise<SegmentsResponse>;
}

export function buildSegmentsExportUrl(
  params: FetchSegmentsParams = {},
): string {
  const query = new URLSearchParams();
  if (params.include_withdrawn) query.set("include_withdrawn", "true");
  if (params.include_blocked) query.set("include_blocked", "true");
  const qs = query.toString();
  return `${API_BASE}/api/v1/admin/analytics/segments/export${qs ? `?${qs}` : ""}`;
}

export async function fetchSegmentsExport(
  params: FetchSegmentsParams = {},
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(buildSegmentsExportUrl(params), {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`segments export failed: ${res.status}`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await res.blob(),
    filename:
      match?.[1] ?? `segments_${new Date().toISOString().slice(0, 10)}.xlsx`,
  };
}

// ---------------------------------------------------------------------------
// Story 5.5: 매출 + 토큰비용 차액 + 엑셀 export
// ---------------------------------------------------------------------------

export interface RevenueVarianceResponse {
  year_month: string;
  /** @deprecated gross_revenue_krw 와 동일 (하위호환 alias) */
  revenue_krw: number;
  gross_revenue_krw: number;
  refund_krw: number;
  net_revenue_krw: number;
  token_cost_usd: string;
  token_cost_krw: number;
  usd_to_krw: number;
  /** net_revenue_krw - token_cost_krw */
  variance_krw: number;
  error_count: number;
  anomaly_count: number;
  applied_filters: {
    year_month: string;
    kst_start: string;
    kst_end_exclusive: string;
  };
}

export interface RevenueSeriesItem {
  year_month: string;
  /** @deprecated gross_revenue_krw 와 동일 (하위호환 alias) */
  revenue_krw: number;
  gross_revenue_krw: number;
  refund_krw: number;
  net_revenue_krw: number;
  token_cost_krw: number;
  variance_krw: number;
}

export interface RevenueSeriesResponse {
  months: number;
  to: string;
  from: string;
  usd_to_krw: number;
  items: RevenueSeriesItem[];
}

export async function fetchRevenueVariance(
  params: { year_month?: string } = {},
): Promise<RevenueVarianceResponse> {
  const query = new URLSearchParams();
  if (params.year_month) query.set("year_month", params.year_month);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/revenue-variance${qs ? `?${qs}` : ""}`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error(`revenue-variance fetch failed: ${res.status}`);
  return res.json() as Promise<RevenueVarianceResponse>;
}

export async function fetchRevenueVarianceSeries(
  params: { months?: number; to?: string } = {},
): Promise<RevenueSeriesResponse> {
  const query = new URLSearchParams();
  if (params.months) query.set("months", String(params.months));
  if (params.to) query.set("to", params.to);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/revenue-variance/series${qs ? `?${qs}` : ""}`,
    { credentials: "include" },
  );
  if (!res.ok)
    throw new Error(`revenue-variance series fetch failed: ${res.status}`);
  return res.json() as Promise<RevenueSeriesResponse>;
}

export async function fetchRevenueVarianceExport(
  params: { year_month: string },
): Promise<{ blob: Blob; filename: string }> {
  const query = new URLSearchParams({ year_month: params.year_month });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/analytics/revenue-variance/export?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error(`revenue-variance export failed: ${res.status}`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await res.blob(),
    filename: match?.[1] ?? `revenue_variance_${params.year_month}.xlsx`,
  };
}
