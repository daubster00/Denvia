"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  buildQuestionsExportUrl,
  fetchQuestions,
  type QuestionsSort,
  type QuestionsUnit,
} from "@/features/admin-dashboard/api/analytics";
import {
  DashboardChart,
  type ChartSeries,
} from "@/features/admin-dashboard/components/DashboardChart";
import styles from "./page.module.css";

const UNITS: { value: QuestionsUnit; label: string; hint: string }[] = [
  { value: "day", label: "일별", hint: "최근 30일" },
  { value: "week", label: "주별", hint: "최근 12주" },
  { value: "month", label: "월별", hint: "최근 12개월" },
  { value: "year", label: "연도별", hint: "최근 5년" },
];

const SORTS: { value: QuestionsSort; label: string }[] = [
  { value: "latest", label: "최신순" },
  { value: "tokens", label: "토큰많은순" },
  { value: "email", label: "계정순" },
];

const SERIES: ChartSeries[] = [
  { key: "count", label: "질문 수", tone: "brand" },
];

const PER_PAGE = 20;

export default function QuestionsAnalyticsPage() {
  const [unit, setUnit] = useState<QuestionsUnit>("day");
  const [sort, setSort] = useState<QuestionsSort>("latest");
  const [page, setPage] = useState(1);
  const activeUnit = UNITS.find((u) => u.value === unit) ?? UNITS[0];

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "questions", { unit, sort, page }],
    queryFn: () =>
      fetchQuestions({ unit, sort, page, per_page: PER_PAGE }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const chartData = useMemo(
    () =>
      data?.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, unit),
        count: b.count,
      })) ?? [],
    [data, unit],
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1;

  function handleUnitChange(next: QuestionsUnit) {
    setUnit(next);
    setPage(1);
  }

  function handleSortChange(next: QuestionsSort) {
    setSort(next);
    setPage(1);
  }

  return (
    <section className={styles.page} aria-labelledby="questions-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="questions-title" className={styles.title}>
            질문 통계
          </h1>
          <p className={styles.caption}>
            사용자가 챗봇에 보낸 질문을 일/주/월/년 단위로 합산해서 보여줍니다.
            아래 목록에서 정렬을 바꾸면 같은 기간의 실제 질문·답변 내용을
            확인할 수 있고, 엑셀로 내려받을 수도 있습니다.
          </p>
        </div>
        <div className={styles.headerActions}>
          <a
            className={styles.exportBtn}
            href={buildQuestionsExportUrl({ unit, sort })}
            aria-label="현재 조건으로 엑셀 내려받기"
          >
            ⬇ 엑셀 내려받기
          </a>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={() => refetch()}
            aria-label="질문 통계 새로고침"
            disabled={isFetching}
          >
            ↻ 새로고침
          </button>
        </div>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="필터">
        <div className={styles.toggleGroup}>
          <span className={styles.toggleLabel}>집계 단위</span>
          <div
            className={styles.unitToggle}
            role="group"
            aria-label="집계 단위"
          >
            {UNITS.map((u) => (
              <button
                key={u.value}
                type="button"
                className={
                  unit === u.value ? styles.unitButtonActive : styles.unitButton
                }
                aria-pressed={unit === u.value}
                onClick={() => handleUnitChange(u.value)}
              >
                {u.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.toggleGroup}>
          <span className={styles.toggleLabel}>정렬</span>
          <div className={styles.unitToggle} role="group" aria-label="정렬">
            {SORTS.map((s) => (
              <button
                key={s.value}
                type="button"
                className={
                  sort === s.value ? styles.unitButtonActive : styles.unitButton
                }
                aria-pressed={sort === s.value}
                onClick={() => handleSortChange(s.value)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          질문 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>질문 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && (
        <>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>총 질문 수</p>
              <p className={styles.summaryValue}>
                {data.total_count.toLocaleString()}건
              </p>
              <p className={styles.summaryHint}>
                {activeUnit.hint} ({data.from} ~ {data.to}) 동안 누적된 질문 수
              </p>
            </div>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>표시 중 질문</p>
              <p className={styles.summaryValue}>
                {data.total.toLocaleString()}건
              </p>
              <p className={styles.summaryHint}>
                현재 필터 조건에 맞는 상세 항목 수
              </p>
            </div>
          </div>

          <div className={styles.chartBox}>
            <h2 className={styles.chartTitle}>
              {activeUnit.label} 질문 추이
            </h2>
            {chartData.length === 0 ? (
              <p className={styles.statusMessage}>
                해당 구간에 질문 기록이 없습니다.
              </p>
            ) : (
              <DashboardChart
                variant="line"
                data={chartData}
                xKey="bucket_start"
                series={SERIES}
                height={260}
                ariaLabel={`${activeUnit.label} 질문 수 추세`}
              />
            )}
          </div>

          <div className={styles.tableBox}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>작성일시 (KST)</th>
                  <th>계정</th>
                  <th>가입유형</th>
                  <th>질문 / 답변</th>
                  <th className={styles.numCell}>토큰 (입력+출력)</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={5}>해당 조건의 질문이 없습니다.</td>
                  </tr>
                ) : (
                  data.items.map((it) => (
                    <tr key={it.qa_log_id}>
                      <td>{formatDateTime(it.created_at)}</td>
                      <td>{it.email ?? "(비회원)"}</td>
                      <td>{segmentLabel(it.segment)}</td>
                      <td>
                        <div className={styles.qaCell}>
                          <p className={styles.qText}>Q. {it.question_text}</p>
                          <p className={styles.aText}>
                            A.{" "}
                            {it.answer_text
                              ? truncate(it.answer_text, 240)
                              : statusFallback(it.status)}
                          </p>
                        </div>
                      </td>
                      <td className={styles.numCell}>
                        {it.total_tokens.toLocaleString()}
                        <span className={styles.tokenBreakdown}>
                          ({it.input_tokens.toLocaleString()}+
                          {it.output_tokens.toLocaleString()})
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            {data.items.length > 0 && (
              <div className={styles.pagination}>
                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || isFetching}
                >
                  ← 이전
                </button>
                <span className={styles.pageInfo}>
                  {page} / {totalPages} 쪽
                </span>
                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || isFetching}
                >
                  다음 →
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function formatBucket(iso: string, unit: QuestionsUnit): string {
  const [y, m, d] = iso.split("-");
  if (unit === "year") return `${y}년`;
  if (unit === "month") return `${y}-${m}`;
  if (unit === "week") return `${m}-${d} 주`;
  return `${m}-${d}`;
}

function formatDateTime(iso: string): string {
  // iso e.g. 2026-05-26T09:23:00+09:00
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

function segmentLabel(seg: string | null): string {
  if (!seg) return "—";
  if (seg === "doctor") return "치과의사";
  if (seg === "hygienist") return "치과위생사";
  if (seg === "student_other") return "학생/기타";
  return seg;
}

function statusFallback(status: string | null): string {
  if (status === "in_progress") return "(스트리밍 진행 중 — 응답 미저장)";
  if (status === "error") return "(응답 생성 실패)";
  return "(응답 없음)";
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}
