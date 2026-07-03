/**
 * #113 질의응답 검토 — API 클라이언트.
 *
 * 백엔드 `/api/v1/admin/qa-review*` 와 1:1. 스타일은 admin-dashboard/api/analytics.ts 준수.
 * - 목록/통계 조회, 굿/베드 평가 토글, 베드 코멘트 저장, 검토완료 토글, 선택 삭제, 엑셀, 설정.
 * - sub_operator(부운영자) 응답에는 `user` 필드가 아예 없다.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const BASE_PATH = "/api/v1/admin/qa-review";

// ── 공통 타입 ────────────────────────────────────────────────────────────────

export type QaPeriod = "today" | "3d" | "7d" | "month" | "custom";
export type QaRatingFilter = "all" | "good" | "bad" | "unrated";
export type QaReviewFilter = "all" | "reviewed" | "unreviewed";
export type QaRating = "good" | "bad";
export type QaBucket = "day" | "week" | "month";

/** 한 질의응답 행의 검토 상태. */
export interface QaReviewState {
  rating: "good" | "bad" | null;
  comment: string | null;
  change_count: number;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  /** 평가 메모를 작성한 관리자 계정(이메일). */
  rated_by_name: string | null;
  /** 평가/메모를 마지막으로 저장한 시각(KST ISO). 작성자 계정 옆에 표기. */
  rated_at: string | null;
}

export interface QaReviewUser {
  user_id: number | null;
  email: string | null;
  segment: string | null;
}

export interface QaReviewItem {
  qa_log_id: number;
  question: string;
  answer: string | null;
  created_at: string | null;
  review: QaReviewState;
  /** sub_operator(부운영자) 응답에는 이 필드가 아예 없다. */
  user?: QaReviewUser;
}

/**
 * rate/comment/complete 공통 응답(백엔드 ReviewActionResponse).
 * 목록의 QaReviewState 와 달리 reviewed_by_name 이 없고 reviewed 플래그가 있다.
 * → 목록 캐시에는 겹치는 필드만 부분 병합한다.
 */
export interface QaReviewActionResult {
  qa_log_id: number;
  rating: "good" | "bad" | null;
  comment: string | null;
  change_count: number;
  reviewed_at: string | null;
  reviewed: boolean | null;
  /** 평가/메모를 마지막으로 저장한 시각(KST ISO). */
  rated_at: string | null;
}

export interface QaEffectivePeriod {
  date_from: string;
  date_to: string;
  /** 부운영자 조회기간 상한에 걸려 시작일이 당겨졌으면 true. */
  clamped: boolean;
  max_lookback_days: number;
}

export interface QaReviewListResponse {
  items: QaReviewItem[];
  total: number;
  page: number;
  page_size: number;
  viewer_grade: string;
  effective_period: QaEffectivePeriod;
}

export interface FetchQaReviewListParams {
  period?: QaPeriod;
  date_from?: string;
  date_to?: string;
  rating?: QaRatingFilter;
  review?: QaReviewFilter;
  q?: string;
  page?: number;
  page_size?: number;
}

function buildListQuery(params: FetchQaReviewListParams): URLSearchParams {
  const query = new URLSearchParams();
  if (params.period) query.set("period", params.period);
  if (params.date_from) query.set("date_from", params.date_from);
  if (params.date_to) query.set("date_to", params.date_to);
  if (params.rating) query.set("rating", params.rating);
  if (params.review) query.set("review", params.review);
  if (params.q) query.set("q", params.q);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  return query;
}

export async function fetchQaReviewList(
  params: FetchQaReviewListParams = {},
): Promise<QaReviewListResponse> {
  const qs = buildListQuery(params).toString();
  const res = await fetch(`${API_BASE}${BASE_PATH}${qs ? `?${qs}` : ""}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`qa-review list fetch failed: ${res.status}`);
  return res.json() as Promise<QaReviewListResponse>;
}

// ── 통계 (master/operator 전용) ──────────────────────────────────────────────

export interface QaReviewSummary {
  good_count: number;
  bad_count: number;
  reviewed_count: number;
  good_ratio: number | null;
}

export interface QaReviewSeriesItem {
  bucket: string;
  good: number;
  bad: number;
  good_ratio: number | null;
}

export interface QaReviewSummaryResponse {
  summary: QaReviewSummary;
  series: QaReviewSeriesItem[];
}

export interface FetchQaReviewSummaryParams {
  period?: QaPeriod;
  date_from?: string;
  date_to?: string;
  bucket?: QaBucket;
}

export async function fetchQaReviewSummary(
  params: FetchQaReviewSummaryParams = {},
): Promise<QaReviewSummaryResponse> {
  const query = new URLSearchParams();
  if (params.period) query.set("period", params.period);
  if (params.date_from) query.set("date_from", params.date_from);
  if (params.date_to) query.set("date_to", params.date_to);
  if (params.bucket) query.set("bucket", params.bucket);
  const qs = query.toString();
  const res = await fetch(
    `${API_BASE}${BASE_PATH}/summary${qs ? `?${qs}` : ""}`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error(`qa-review summary fetch failed: ${res.status}`);
  return res.json() as Promise<QaReviewSummaryResponse>;
}

// ── 평가 / 코멘트 / 검토완료 / 삭제 ──────────────────────────────────────────

/**
 * 평가 저장 — SET 시맨틱(#113 모달 개편).
 * rating: "good"|"bad" 로 설정, null 이면 평가 해제. comment 는 평가 메모(굿/베드 공통).
 */
export async function rateQaReview(
  qaLogId: number,
  body: { rating: QaRating | null; comment?: string | null },
): Promise<QaReviewActionResult> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/${qaLogId}/rate`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`qa-review rate failed: ${res.status}`);
  return res.json() as Promise<QaReviewActionResult>;
}

/** 베드 코멘트 저장. */
export async function saveQaReviewComment(
  qaLogId: number,
  comment: string,
): Promise<QaReviewActionResult> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/${qaLogId}/comment`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) throw new Error(`qa-review comment save failed: ${res.status}`);
  return res.json() as Promise<QaReviewActionResult>;
}

/** 검토완료 토글 (master/operator 전용). */
export async function completeQaReview(
  qaLogId: number,
  reviewed: boolean,
): Promise<QaReviewActionResult> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/${qaLogId}/complete`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed }),
  });
  if (!res.ok) throw new Error(`qa-review complete failed: ${res.status}`);
  return res.json() as Promise<QaReviewActionResult>;
}

export interface QaBulkDeleteResponse {
  deleted: number;
}

/** 선택 삭제 (master/operator 전용). */
export async function bulkDeleteQaReview(
  qaLogIds: number[],
): Promise<QaBulkDeleteResponse> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/bulk-delete`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qa_log_ids: qaLogIds }),
  });
  if (!res.ok) throw new Error(`qa-review bulk-delete failed: ${res.status}`);
  return res.json() as Promise<QaBulkDeleteResponse>;
}

// ── 엑셀 (master/operator 전용) ──────────────────────────────────────────────

export function buildQaReviewExportUrl(
  params: Omit<FetchQaReviewListParams, "page" | "page_size">,
): string {
  const query = buildListQuery(params);
  const qs = query.toString();
  return `${API_BASE}${BASE_PATH}/export${qs ? `?${qs}` : ""}`;
}

// ── 설정 (master/operator 전용) ──────────────────────────────────────────────

export interface QaReviewSettings {
  sub_operator_max_lookback_days: number;
}

export async function fetchQaReviewSettings(): Promise<QaReviewSettings> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/settings`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`qa-review settings fetch failed: ${res.status}`);
  return res.json() as Promise<QaReviewSettings>;
}

export async function updateQaReviewSettings(
  settings: QaReviewSettings,
): Promise<QaReviewSettings> {
  const res = await fetch(`${API_BASE}${BASE_PATH}/settings`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error(`qa-review settings update failed: ${res.status}`);
  return res.json() as Promise<QaReviewSettings>;
}
