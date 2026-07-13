"use client";

/**
 * #130-③ 질의응답 검토 부관리자 활동 리포트 (급여 산정용).
 *
 * 최고관리자(master/operator)가 부관리자를 골라 설정한 기간의 검토 활동을 확인한다.
 * - 부관리자별 굿/베드/피드백 개수 요약 표.
 * - 특정 부관리자 선택 시 각 검토의 표시 라벨('굿(피드백작성)' 등) 상세 리스트.
 *
 * 전체 열람 등급(master/operator)만 접근. 백엔드가 403 으로도 이중 차단한다.
 * 레퍼런스: /admin/qa-review (기간필터·표·CSS Modules 관례 준수).
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import {
  fetchQaReviewerActivity,
  type QaReviewerActivityRow,
} from "@/features/admin-qa-review/api";
import styles from "./page.module.css";

// ── 기간 helpers (KST 기준 YYYY-MM-DD 문자열) ────────────────────────────────
function todayKstDateStr(): string {
  const kstMs = Date.now() + 9 * 60 * 60 * 1000;
  return new Date(kstMs).toISOString().slice(0, 10);
}

/** 이번 달 1일 ~ 오늘. 급여는 월 단위 집계가 기본이므로 초기값으로 쓴다. */
function monthStartKstDateStr(): string {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  return `${yyyy}-${mm}-01`;
}

/** 특정 연·월(1-based)의 1일 ~ 말일 문자열 쌍. */
function monthRange(year: number, month1: number): { from: string; to: string } {
  const mm = String(month1).padStart(2, "0");
  const from = `${year}-${mm}-01`;
  // 다음 달 0일 = 이번 달 말일.
  const lastDay = new Date(Date.UTC(year, month1, 0)).getUTCDate();
  const to = `${year}-${mm}-${String(lastDay).padStart(2, "0")}`;
  return { from, to };
}

/** 최근 N개월 프리셋 라벨(현재 달 포함). */
function recentMonthPresets(count: number): { label: string; year: number; month1: number }[] {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const out: { label: string; year: number; month1: number }[] = [];
  let y = kst.getUTCFullYear();
  let m = kst.getUTCMonth() + 1; // 1-based
  for (let i = 0; i < count; i += 1) {
    out.push({ label: `${y}.${String(m).padStart(2, "0")}`, year: y, month1: m });
    m -= 1;
    if (m === 0) {
      m = 12;
      y -= 1;
    }
  }
  return out;
}

export default function QaReviewerActivityPage() {
  const admin = useAdminSessionStore((s) => s.admin);
  // 전체 열람 등급만 접근(부관리자는 타인 급여 데이터 열람 불가).
  const privileged =
    admin?.admin_grade === "master" ||
    admin?.admin_grade === "operator" ||
    admin?.admin_grade == null;

  const monthPresets = useMemo(() => recentMonthPresets(6), []);

  const [dateFrom, setDateFrom] = useState<string>(monthStartKstDateStr());
  const [dateTo, setDateTo] = useState<string>(todayKstDateStr());
  // 선택된 부관리자(요약 표에서 클릭 → 상세). null = 전체 요약만.
  const [selectedReviewerId, setSelectedReviewerId] = useState<number | null>(null);

  // 요약 리스트(전체 부관리자) — 항상 조회.
  const summaryQuery = useQuery({
    queryKey: ["admin", "qa-review", "activity", "summary", dateFrom, dateTo],
    queryFn: () => fetchQaReviewerActivity({ date_from: dateFrom, date_to: dateTo }),
    enabled: privileged && Boolean(dateFrom) && Boolean(dateTo),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // 특정 부관리자 상세 — 선택됐을 때만.
  const detailQuery = useQuery({
    queryKey: [
      "admin",
      "qa-review",
      "activity",
      "detail",
      dateFrom,
      dateTo,
      selectedReviewerId,
    ],
    queryFn: () =>
      fetchQaReviewerActivity({
        date_from: dateFrom,
        date_to: dateTo,
        reviewer_id: selectedReviewerId ?? undefined,
      }),
    enabled:
      privileged &&
      selectedReviewerId != null &&
      Boolean(dateFrom) &&
      Boolean(dateTo),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const reviewers: QaReviewerActivityRow[] = summaryQuery.data?.reviewers ?? [];

  // 합계 행 — 급여 산정 시 전체 규모를 한눈에.
  const totals = useMemo(() => {
    return reviewers.reduce(
      (acc, r) => {
        acc.good += r.good_count;
        acc.bad += r.bad_count;
        acc.feedback += r.feedback_count;
        return acc;
      },
      { good: 0, bad: 0, feedback: 0 },
    );
  }, [reviewers]);

  const selectedReviewer = reviewers.find(
    (r) => r.reviewer_id === selectedReviewerId,
  );
  const detailItems = detailQuery.data?.detail ?? [];

  function applyMonthPreset(year: number, month1: number) {
    const { from, to } = monthRange(year, month1);
    setDateFrom(from);
    setDateTo(to);
    setSelectedReviewerId(null);
  }

  if (!privileged) {
    return (
      <section className={styles.page}>
        <p className={styles.statusMessage} role="status">
          이 페이지는 전체 열람 권한을 가진 관리자만 이용할 수 있습니다.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.page} aria-labelledby="qa-activity-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin/qa-review" className={styles.backLink}>
            ← 질의응답 검토로
          </Link>
          <h1 id="qa-activity-title" className={styles.title}>
            부관리자 검토 활동 리포트
          </h1>
          <p className={styles.caption}>
            선택한 기간 동안 부관리자별 굿·베드·피드백 활동을 집계합니다. (급여 산정용)
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => {
            void summaryQuery.refetch();
            if (selectedReviewerId != null) void detailQuery.refetch();
          }}
          disabled={summaryQuery.isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      {/* 기간 필터 */}
      <div className={styles.filters} role="toolbar" aria-label="기간 필터">
        <div className={styles.monthPresets}>
          {monthPresets.map((p) => {
            const range = monthRange(p.year, p.month1);
            const active = dateFrom === range.from && dateTo === range.to;
            return (
              <button
                key={p.label}
                type="button"
                className={active ? styles.presetBtnActive : styles.presetBtn}
                aria-pressed={active}
                onClick={() => applyMonthPreset(p.year, p.month1)}
              >
                {p.label}
              </button>
            );
          })}
        </div>

        <div className={styles.dateRange}>
          <label className={styles.dateLabel}>
            <span className={styles.dateLabelText}>시작일</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setSelectedReviewerId(null);
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
                setSelectedReviewerId(null);
              }}
              className={styles.dateInput}
              aria-label="종료일"
            />
          </label>
        </div>
      </div>

      {/* 요약 표 */}
      {summaryQuery.isLoading && (
        <p className={styles.statusMessage} role="status">
          활동을 집계하는 중…
        </p>
      )}
      {summaryQuery.isError && (
        <section className={styles.errorBox} role="alert">
          <p>활동 집계를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => void summaryQuery.refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {summaryQuery.data && !summaryQuery.isLoading && !summaryQuery.isError && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">부관리자</th>
                <th scope="col">굿</th>
                <th scope="col">베드</th>
                <th scope="col">피드백</th>
                <th scope="col">상세</th>
              </tr>
            </thead>
            <tbody>
              {reviewers.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyRow}>
                    이 기간에 검토 활동이 있는 부관리자가 없습니다.
                  </td>
                </tr>
              ) : (
                reviewers.map((r) => {
                  const active = r.reviewer_id === selectedReviewerId;
                  return (
                    <tr
                      key={r.reviewer_id}
                      className={active ? styles.rowActive : undefined}
                    >
                      <td className={styles.cellEmail}>
                        {r.reviewer_email ?? `#${r.reviewer_id}`}
                      </td>
                      <td className={styles.cellNum}>
                        {r.good_count.toLocaleString()}
                      </td>
                      <td className={styles.cellNum}>
                        {r.bad_count.toLocaleString()}
                      </td>
                      <td className={styles.cellNum}>
                        {r.feedback_count.toLocaleString()}
                      </td>
                      <td className={styles.cellAction}>
                        <button
                          type="button"
                          className={styles.detailBtn}
                          aria-pressed={active}
                          onClick={() =>
                            setSelectedReviewerId(active ? null : r.reviewer_id)
                          }
                        >
                          {active ? "닫기" : "상세 보기"}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
            {reviewers.length > 0 && (
              <tfoot>
                <tr className={styles.totalRow}>
                  <td className={styles.cellEmail}>합계</td>
                  <td className={styles.cellNum}>{totals.good.toLocaleString()}</td>
                  <td className={styles.cellNum}>{totals.bad.toLocaleString()}</td>
                  <td className={styles.cellNum}>
                    {totals.feedback.toLocaleString()}
                  </td>
                  <td className={styles.cellAction} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      {/* 특정 부관리자 상세 */}
      {selectedReviewerId != null && (
        <section className={styles.detailSection} aria-live="polite">
          <h2 className={styles.detailTitle}>
            {selectedReviewer?.reviewer_email ?? `#${selectedReviewerId}`} 상세
            {selectedReviewer && (
              <span className={styles.detailSummary}>
                굿 {selectedReviewer.good_count.toLocaleString()} · 베드{" "}
                {selectedReviewer.bad_count.toLocaleString()} · 피드백{" "}
                {selectedReviewer.feedback_count.toLocaleString()}
              </span>
            )}
          </h2>

          {detailQuery.isLoading && (
            <p className={styles.statusMessage} role="status">
              상세를 불러오는 중…
            </p>
          )}
          {detailQuery.isError && (
            <p className={styles.actionError} role="alert">
              상세를 불러오지 못했습니다.
            </p>
          )}

          {detailQuery.data && !detailQuery.isLoading && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">질의 ID</th>
                    <th scope="col">활동</th>
                    <th scope="col">피드백 내용</th>
                    <th scope="col">평가 시각</th>
                  </tr>
                </thead>
                <tbody>
                  {detailItems.length === 0 ? (
                    <tr>
                      <td colSpan={4} className={styles.emptyRow}>
                        이 기간에 이 부관리자의 검토 기록이 없습니다.
                      </td>
                    </tr>
                  ) : (
                    detailItems.map((d) => (
                      <tr key={d.qa_log_id}>
                        <td className={styles.cellNum}>{d.qa_log_id}</td>
                        <td>
                          <span
                            className={
                              d.rating === "good"
                                ? styles.badgeGood
                                : d.rating === "bad"
                                  ? styles.badgeBad
                                  : styles.badgeNeutral
                            }
                          >
                            {d.label}
                          </span>
                        </td>
                        <td className={styles.cellComment}>
                          {d.comment ?? "—"}
                        </td>
                        <td className={styles.cellTime}>{d.rated_at ?? "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </section>
  );
}
