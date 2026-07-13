"use client";

/**
 * #113 질의응답 검토.
 *
 * 운영진이 사용자 질의응답(질문+답변)을 보고 굿/베드로 답변 품질을 검토한다.
 * - 부운영자(sub_operator): 질문·답변·굿베드·베드코멘트만. 통계/엑셀/설정/검토완료/삭제/체크박스/사용자정보는 감춘다.
 * - 운영관리자·마스터(operator/master): 전체 기능.
 *
 * 레퍼런스: /admin/dashboard/analytics/feedback (기간필터·%표시·엑셀·검토완료·삭제 패턴).
 */

import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { DashboardChart } from "@/features/admin-dashboard/components/DashboardChart";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import { QaReviewRow } from "@/features/admin-qa-review/components/QaReviewRow";
import { QaReviewModal } from "@/features/admin-qa-review/components/QaReviewModal";
import {
  bulkDeleteQaReview,
  buildQaReviewExportUrl,
  completeQaReview,
  fetchQaReviewList,
  fetchQaReviewSettings,
  fetchQaReviewSummary,
  rateQaReview,
  updateQaReviewSettings,
  type FetchQaReviewListParams,
  type QaBucket,
  type QaPeriod,
  type QaRating,
  type QaRatingFilter,
  type QaReviewFilter,
  type QaReviewItem,
  type QaReviewListResponse,
  type QaReviewState,
} from "@/features/admin-qa-review/api";
import styles from "./page.module.css";

const PERIODS: { value: QaPeriod; label: string }[] = [
  { value: "today", label: "당일" },
  { value: "3d", label: "3일" },
  { value: "7d", label: "7일" },
  { value: "month", label: "한달" },
  { value: "custom", label: "특정일자" },
];

const RATING_FILTERS: { value: QaRatingFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "good", label: "굿만" },
  { value: "bad", label: "베드만" },
  { value: "unrated", label: "미평가" },
];

const REVIEW_FILTERS: { value: QaReviewFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "reviewed", label: "검토완료" },
  { value: "unreviewed", label: "미검토" },
];

const BUCKETS: { value: QaBucket; label: string }[] = [
  { value: "day", label: "일" },
  { value: "week", label: "주" },
  { value: "month", label: "월" },
];

// 부운영자 조회기간 상한 설정 옵션 (일 단위).
const LOOKBACK_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "당일" },
  { value: 3, label: "3일" },
  { value: 7, label: "7일" },
  { value: 30, label: "한달" },
];

const PAGE_SIZE = 50;

function formatBucketLabel(bucket: string): string {
  if (!bucket) return bucket;
  const [y, m, d] = bucket.split("-");
  if (!y || !m) return bucket;
  if (!d) return `${y}-${m}`;
  return `${m}/${d}`;
}

export default function QaReviewPage() {
  const admin = useAdminSessionStore((s) => s.admin);
  // 최고관리자(= 운영관리자 operator + 마스터 master) → 전체 기능.
  // 부관리자(sub_operator) → 제한. (등급 백필 누락 null 은 방어적으로 전체 허용)
  const privileged =
    admin?.admin_grade === "master" ||
    admin?.admin_grade === "operator" ||
    admin?.admin_grade == null;

  const qc = useQueryClient();

  // 필터 상태
  const [period, setPeriod] = useState<QaPeriod>("7d");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [rating, setRating] = useState<QaRatingFilter>("all");
  const [review, setReview] = useState<QaReviewFilter>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [bucket, setBucket] = useState<QaBucket>("day");

  // 선택 삭제
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  // 진행 중인 행별 작업 표시
  const [completePending, setCompletePending] = useState<Set<number>>(() => new Set());
  const [actionError, setActionError] = useState<string | null>(null);

  // 상세/평가 모달 — 클릭한 항목 id. 실제 데이터는 목록 캐시에서 파생해 갱신을 반영.
  const [activeId, setActiveId] = useState<number | null>(null);

  // 설정 패널
  const [settingsOpen, setSettingsOpen] = useState(false);

  const listParams: FetchQaReviewListParams = useMemo(
    () => ({
      period,
      date_from: period === "custom" ? dateFrom || undefined : undefined,
      date_to: period === "custom" ? dateTo || undefined : undefined,
      rating,
      review,
      q: q || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    [period, dateFrom, dateTo, rating, review, q, page],
  );

  const listQueryKey = useMemo(
    () => ["admin", "qa-review", "list", listParams] as const,
    [listParams],
  );

  const {
    data,
    error,
    isLoading,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: listQueryKey,
    queryFn: () => fetchQaReviewList(listParams),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const summaryParams = useMemo(
    () => ({
      period,
      date_from: period === "custom" ? dateFrom || undefined : undefined,
      date_to: period === "custom" ? dateTo || undefined : undefined,
      bucket,
    }),
    [period, dateFrom, dateTo, bucket],
  );

  const { data: summaryData } = useQuery({
    queryKey: ["admin", "qa-review", "summary", summaryParams],
    queryFn: () => fetchQaReviewSummary(summaryParams),
    enabled: privileged,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const { data: settings } = useQuery({
    queryKey: ["admin", "qa-review", "settings"],
    queryFn: fetchQaReviewSettings,
    enabled: privileged && settingsOpen,
    staleTime: 60_000,
  });

  const settingsMutation = useMutation({
    mutationFn: (days: number) =>
      updateQaReviewSettings({ sub_operator_max_lookback_days: days }),
    onSuccess: (updated) => {
      qc.setQueryData(["admin", "qa-review", "settings"], updated);
    },
  });

  // 목록 캐시에서 특정 행의 review 상태를 부분 병합.
  // 액션 응답에는 reviewed_by_name 이 없으므로 기존 값 위에 겹치는 필드만 덮어쓴다.
  const patchReview = useCallback(
    (qaLogId: number, patch: Partial<QaReviewState>) => {
      qc.setQueryData<QaReviewListResponse>(listQueryKey, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((it) =>
            it.qa_log_id === qaLogId
              ? { ...it, review: { ...it.review, ...patch } }
              : it,
          ),
        };
      });
    },
    [qc, listQueryKey],
  );

  function withPending(
    setter: React.Dispatch<React.SetStateAction<Set<number>>>,
    id: number,
    on: boolean,
  ) {
    setter((prev) => {
      const nextSet = new Set(prev);
      if (on) nextSet.add(id);
      else nextSet.delete(id);
      return nextSet;
    });
  }

  // 모달 저장 — 평가(굿/베드/해제) + 메모를 한 번의 rate 호출로 반영(SET 시맨틱).
  // 실패 시 throw 하여 모달이 열린 채 자체 에러를 표시하도록 한다.
  const handleModalSave = useCallback(
    async (item: QaReviewItem, rating: QaRating | null, comment: string) => {
      const id = item.qa_log_id;
      const res = await rateQaReview(id, { rating, comment });
      patchReview(id, {
        rating: res.rating,
        comment: res.comment,
        change_count: res.change_count,
        reviewed_at: res.reviewed_at,
        // 평가 응답에는 작성자 이름이 없으므로, 방금 저장한 관리자 계정으로 낙관적 갱신.
        // 평가를 해제(rating=null)하면 메모도 사라지므로 작성자·작성일자도 비운다.
        rated_by_name: res.rating == null ? null : admin?.email ?? null,
        rated_at: res.rating == null ? null : res.rated_at,
      });
    },
    [patchReview, admin?.email],
  );

  const handleToggleComplete = useCallback(
    async (item: QaReviewItem) => {
      const id = item.qa_log_id;
      const nextReviewed = item.review.reviewed_at == null;
      withPending(setCompletePending, id, true);
      setActionError(null);
      try {
        const res = await completeQaReview(id, nextReviewed);
        patchReview(id, { reviewed_at: res.reviewed_at });
      } catch {
        setActionError("검토완료 처리에 실패했습니다. 잠시 후 다시 시도해 주세요.");
      } finally {
        withPending(setCompletePending, id, false);
      }
    },
    [patchReview],
  );

  const handleToggleSelect = useCallback((qaLogId: number, next: boolean) => {
    setSelectedIds((prev) => {
      const nextSet = new Set(prev);
      if (next) nextSet.add(qaLogId);
      else nextSet.delete(qaLogId);
      return nextSet;
    });
  }, []);

  const handleBulkDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    const confirmed = window.confirm(
      `선택한 ${selectedIds.size}건을 삭제하시겠습니까?\n삭제하면 검토 목록에서 사라집니다. 되돌릴 수 없습니다.`,
    );
    if (!confirmed) return;
    setActionError(null);
    try {
      await bulkDeleteQaReview(Array.from(selectedIds));
      setSelectedIds(new Set());
      await qc.invalidateQueries({ queryKey: ["admin", "qa-review", "list"] });
    } catch {
      setActionError("선택 삭제에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    }
  }, [selectedIds, qc]);

  const handleExport = useCallback(() => {
    const url = buildQaReviewExportUrl({
      period,
      date_from: period === "custom" ? dateFrom || undefined : undefined,
      date_to: period === "custom" ? dateTo || undefined : undefined,
      rating,
      review,
      q: q || undefined,
    });
    const iframe = document.createElement("iframe");
    iframe.src = url;
    iframe.hidden = true;
    iframe.title = "qa-review-export-download";
    document.body.appendChild(iframe);
    window.setTimeout(() => iframe.remove(), 60_000);
  }, [period, dateFrom, dateTo, rating, review, q]);

  function resetPage() {
    setPage(1);
  }

  const items = data?.items ?? [];
  // 모달에 넘길 항목은 캐시에서 파생 — 평가/메모 저장 후 patchReview 갱신이 즉시 반영된다.
  const activeItem =
    activeId != null
      ? items.find((it) => it.qa_log_id === activeId) ?? null
      : null;
  const summary = summaryData?.summary;
  const series = useMemo(
    () =>
      (summaryData?.series ?? []).map((b) => ({
        bucket_label: formatBucketLabel(b.bucket),
        good: b.good,
        bad: b.bad,
        good_ratio_pct:
          b.good_ratio != null ? Math.round(b.good_ratio * 1000) / 10 : 0,
      })),
    [summaryData?.series],
  );

  const goodPct =
    summary?.good_ratio != null
      ? `${(summary.good_ratio * 100).toFixed(1)}%`
      : "—";

  const effective = data?.effective_period;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const currentLookback = settings?.sub_operator_max_lookback_days;

  return (
    <section className={styles.page} aria-labelledby="qa-review-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="qa-review-title" className={styles.title}>
            질의응답 검토
          </h1>
          <p className={styles.caption}>
            사용자 질문과 답변을 보고 굿/베드로 답변 품질을 평가합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      {/* 필터 바 */}
      <div className={styles.filters} role="toolbar" aria-label="검토 필터">
        <div className={styles.toggleGroup}>
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              className={period === p.value ? styles.toggleBtnActive : styles.toggleBtn}
              aria-pressed={period === p.value}
              onClick={() => {
                setPeriod(p.value);
                resetPage();
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {period === "custom" && (
          <div className={styles.dateRange}>
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>시작일</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  resetPage();
                }}
                className={styles.dateInput}
                aria-label="시작일"
              />
            </label>
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>종료일</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  resetPage();
                }}
                className={styles.dateInput}
                aria-label="종료일"
              />
            </label>
          </div>
        )}

        <div className={styles.toggleGroup}>
          {RATING_FILTERS.map((rf) => (
            <button
              key={rf.value}
              type="button"
              className={rating === rf.value ? styles.toggleBtnActive : styles.toggleBtn}
              aria-pressed={rating === rf.value}
              onClick={() => {
                setRating(rf.value);
                resetPage();
              }}
            >
              {rf.label}
            </button>
          ))}
        </div>

        <div className={styles.toggleGroup}>
          {REVIEW_FILTERS.map((rf) => (
            <button
              key={rf.value}
              type="button"
              className={review === rf.value ? styles.toggleBtnActive : styles.toggleBtn}
              aria-pressed={review === rf.value}
              onClick={() => {
                setReview(rf.value);
                resetPage();
              }}
            >
              {rf.label}
            </button>
          ))}
        </div>

        <input
          type="search"
          placeholder="질문·답변 키워드 검색"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            resetPage();
          }}
          className={styles.searchInput}
          aria-label="질문·답변 키워드 검색"
        />
      </div>

      {/* 부운영자 조회기간 상한에 걸렸을 때 안내 */}
      {effective?.clamped && (
        <p className={styles.clampNotice} role="status">
          조회 가능한 기간이{" "}
          {effective.max_lookback_days <= 1
            ? "당일"
            : `최근 ${effective.max_lookback_days}일`}
          로 제한되어 있어, 시작일이 {effective.date_from}로 조정되었습니다.
        </p>
      )}

      {/* 통계 영역 — master/operator 전용 */}
      {privileged && (
        <>
          <div className={styles.statsToolbar}>
            <div className={styles.toggleGroup}>
              {BUCKETS.map((b) => (
                <button
                  key={b.value}
                  type="button"
                  className={bucket === b.value ? styles.toggleBtnActive : styles.toggleBtn}
                  aria-pressed={bucket === b.value}
                  onClick={() => setBucket(b.value)}
                >
                  {b.label}
                </button>
              ))}
            </div>

            <div className={styles.toolbarActions}>
              <button
                type="button"
                className={styles.actionBtn}
                onClick={handleExport}
              >
                엑셀 다운로드
              </button>
              <button
                type="button"
                className={styles.actionBtn}
                onClick={() => setSettingsOpen((v) => !v)}
                aria-expanded={settingsOpen}
              >
                설정
              </button>
              <Link
                href="/admin/qa-review/activity"
                className={styles.actionLink}
              >
                부관리자 활동 리포트
              </Link>
              <Link href="/admin/admins/logs" className={styles.actionLink}>
                수정기록 로그
              </Link>
            </div>
          </div>

          {settingsOpen && (
            <div className={styles.settingsPanel}>
              <span className={styles.settingsLabel}>
                부관리자 조회기간 상한
              </span>
              <div className={styles.toggleGroup}>
                {LOOKBACK_OPTIONS.map((opt) => {
                  const active = currentLookback === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      className={active ? styles.toggleBtnActive : styles.toggleBtn}
                      aria-pressed={active}
                      disabled={settingsMutation.isPending}
                      onClick={() => settingsMutation.mutate(opt.value)}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
              {settingsMutation.isError && (
                <span className={styles.settingsError}>
                  설정 저장에 실패했습니다.
                </span>
              )}
            </div>
          )}

          <div className={styles.kpiRow}>
            <KPICard
              label="굿 건수"
              value={`${(summary?.good_count ?? 0).toLocaleString()}건`}
            />
            <KPICard
              label="베드 건수"
              value={`${(summary?.bad_count ?? 0).toLocaleString()}건`}
            />
            <KPICard
              label="검토완료 건수"
              value={`${(summary?.reviewed_count ?? 0).toLocaleString()}건`}
            />
            <p className={styles.ratioText}>굿(정확) 비율: {goodPct}</p>
          </div>

          <div className={styles.chartBox}>
            <DashboardChart
              variant="bar"
              data={series}
              xKey="bucket_label"
              series={[
                { key: "good", label: "굿", tone: "success" },
                { key: "bad", label: "베드", tone: "error" },
              ]}
              height={260}
              ariaLabel={`질의응답 검토 추세 — 굿 ${summary?.good_count ?? 0}건, 베드 ${summary?.bad_count ?? 0}건`}
              emptyMessage="이 기간에 평가된 질의응답이 없습니다."
            />
          </div>
        </>
      )}

      {/* 선택 삭제 바 — master/operator 전용 */}
      {privileged && selectedIds.size > 0 && (
        <div className={styles.bulkBar}>
          <span>{selectedIds.size}건 선택됨</span>
          <button
            type="button"
            className={styles.bulkDeleteBtn}
            onClick={handleBulkDelete}
          >
            선택 삭제
          </button>
        </div>
      )}

      {actionError && (
        <p className={styles.actionError} role="alert">
          {actionError}
        </p>
      )}

      {/* 목록 */}
      {isLoading && (
        <p className={styles.statusMessage} role="status">
          질의응답을 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>질의응답을 불러오지 못했습니다.</p>
          <button type="button" className={styles.retryBtn} onClick={() => refetch()}>
            다시 시도
          </button>
        </section>
      )}

      {data && !isLoading && !error && (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <colgroup>
                {privileged && <col className={styles.colCheck} />}
                <col className={styles.colQuestion} />
                <col className={styles.colAnswer} />
                <col className={styles.colRating} />
                <col className={styles.colStatus} />
                {privileged && <col className={styles.colUser} />}
                <col className={styles.colAction} />
              </colgroup>
              <thead>
                <tr>
                  {privileged && <th className={styles.thCheck} scope="col" />}
                  <th scope="col">질문</th>
                  <th scope="col">답변</th>
                  <th scope="col">평가</th>
                  <th scope="col">상태</th>
                  {privileged && <th scope="col">사용자</th>}
                  <th scope="col">검토</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={privileged ? 7 : 5}
                      className={styles.emptyRow}
                    >
                      조회된 질의응답이 없습니다.
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <QaReviewRow
                      key={item.qa_log_id}
                      item={item}
                      privileged={privileged}
                      selected={selectedIds.has(item.qa_log_id)}
                      onToggleSelect={handleToggleSelect}
                      onOpen={(it) => setActiveId(it.qa_log_id)}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* 페이지네이션 */}
          {data.total > PAGE_SIZE && (
            <div className={styles.pagination}>
              <button
                type="button"
                className={styles.pageBtn}
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                이전
              </button>
              <span className={styles.pageInfo}>
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className={styles.pageBtn}
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                다음
              </button>
            </div>
          )}
        </>
      )}

      {activeItem && (
        <QaReviewModal
          item={activeItem}
          privileged={privileged}
          onClose={() => setActiveId(null)}
          onSave={handleModalSave}
          onToggleComplete={handleToggleComplete}
          completePending={completePending.has(activeItem.qa_log_id)}
        />
      )}
    </section>
  );
}
