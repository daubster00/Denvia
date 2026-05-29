"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  buildQuestionsExportUrl,
  fetchFeedbackDetail,
  fetchQuestions,
  type FeedbackDetail,
  type FeedbackRetrievedDoc,
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

const QUICK_RANGES: { days: number; label: string }[] = [
  { days: 7, label: "최근 7일" },
  { days: 30, label: "최근 30일" },
  { days: 90, label: "최근 90일" },
  { days: 365, label: "최근 1년" },
];

const SERIES: ChartSeries[] = [
  { key: "count", label: "질문 수", tone: "brand" },
];

const PER_PAGE = 20;

const STATS_KEY_ROOT = ["admin", "analytics", "questions", "stats"] as const;
const LIST_KEY_ROOT = ["admin", "analytics", "questions", "list"] as const;

export default function QuestionsAnalyticsPage() {
  // 상단: 추이 그래프(집계 단위)
  const [unit, setUnit] = useState<QuestionsUnit>("day");
  const activeUnit = UNITS.find((u) => u.value === unit) ?? UNITS[0];

  // 하단: 질문/답변 리스트(기간 검색 + 정렬)
  const [listFrom, setListFrom] = useState<string>(() => daysAgoIso(29));
  const [listTo, setListTo] = useState<string>(() => daysAgoIso(0));
  const [sort, setSort] = useState<QuestionsSort>("latest");
  const [page, setPage] = useState(1);

  // 행 클릭 → 전체 화면 오버레이 드로어
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (selectedId === null) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", handleKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [selectedId]);

  const queryClient = useQueryClient();

  const statsQuery = useQuery({
    queryKey: [...STATS_KEY_ROOT, { unit }],
    queryFn: () => fetchQuestions({ unit, per_page: 1, page: 1 }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const listQuery = useQuery({
    queryKey: [
      ...LIST_KEY_ROOT,
      { from: listFrom, to: listTo, sort, page },
    ],
    queryFn: () =>
      fetchQuestions({
        from: listFrom,
        to: listTo,
        sort,
        page,
        per_page: PER_PAGE,
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const detailQuery = useQuery({
    queryKey: ["admin", "analytics", "questions", "detail", selectedId],
    queryFn: () => fetchFeedbackDetail(selectedId as number),
    enabled: selectedId !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const stats = statsQuery.data;
  const list = listQuery.data;

  const chartData = useMemo(
    () =>
      stats?.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, unit),
        count: b.count,
      })) ?? [],
    [stats, unit],
  );

  const totalPages = list ? Math.max(1, Math.ceil(list.total / PER_PAGE)) : 1;

  function handleUnitChange(next: QuestionsUnit) {
    setUnit(next);
  }

  function handleSortChange(next: QuestionsSort) {
    setSort(next);
    setPage(1);
    setSelectedId(null);
  }

  function handlePageChange(next: number) {
    setPage(next);
    setSelectedId(null);
  }

  function handleFromChange(value: string) {
    setListFrom(value);
    setPage(1);
    setSelectedId(null);
  }

  function handleToChange(value: string) {
    setListTo(value);
    setPage(1);
    setSelectedId(null);
  }

  function handleQuickRange(days: number) {
    setListFrom(daysAgoIso(days - 1));
    setListTo(daysAgoIso(0));
    setPage(1);
    setSelectedId(null);
  }

  function handleRowSelect(qaLogId: number) {
    setSelectedId((prev) => (prev === qaLogId ? null : qaLogId));
  }

  function handleRefreshAll() {
    queryClient.invalidateQueries({ queryKey: STATS_KEY_ROOT });
    queryClient.invalidateQueries({ queryKey: LIST_KEY_ROOT });
  }

  const isRefreshing = statsQuery.isFetching || listQuery.isFetching;

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
            위쪽은 선택한 집계 단위(일/주/월/연)로 본 질문 추이입니다. 아래쪽은
            별도의 기간을 직접 지정해 실제 질문·답변 내용을 살펴보고 엑셀로
            내려받을 수 있는 목록입니다. 두 영역의 필터는 서로 영향을 주지
            않습니다.
          </p>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={handleRefreshAll}
            aria-label="질문 통계 새로고침"
            disabled={isRefreshing}
          >
            ↻ 새로고침
          </button>
        </div>
      </header>

      {/* === 상단: 집계 단위 그룹 (그래프 + 수치) === */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionHead}>
          <div className={styles.sectionTitleGroup}>
            <h2 className={styles.sectionTitle}>추이 그래프</h2>
            <p className={styles.sectionHint}>
              아래에서 고른 집계 단위 기준으로 합산해서 그래프와 누적 수치를
              보여줍니다.
            </p>
          </div>
          <div className={styles.sectionActions}>
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
                      unit === u.value
                        ? styles.unitButtonActive
                        : styles.unitButton
                    }
                    aria-pressed={unit === u.value}
                    onClick={() => handleUnitChange(u.value)}
                  >
                    {u.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {statsQuery.isLoading && (
          <p className={styles.statusMessage} role="status">
            그래프 데이터를 불러오는 중…
          </p>
        )}
        {!statsQuery.isLoading && statsQuery.error && (
          <section className={styles.errorBox} role="alert">
            <p>그래프 데이터를 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => statsQuery.refetch()}
            >
              다시 시도
            </button>
          </section>
        )}
        {stats && (
          <>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryItem}>
                <p className={styles.summaryLabel}>
                  {currentPeriodLabel(unit)}
                </p>
                <p className={styles.summaryValue}>
                  {currentBucketCount(stats.buckets).toLocaleString()}건
                </p>
                <p className={styles.summaryHint}>
                  {currentPeriodHint(stats.buckets, unit)}
                </p>
              </div>
              <div className={styles.summaryItem}>
                <p className={styles.summaryLabel}>
                  {unitAverageLabel(unit)}
                </p>
                <p className={styles.summaryValue}>
                  {averagePerBucket(stats.total_count, stats.buckets.length)}건
                </p>
                <p className={styles.summaryHint}>
                  {stats.buckets.length}개 구간 평균
                </p>
              </div>
              <div className={styles.summaryItem}>
                <p className={styles.summaryLabel}>
                  {activeUnit.hint} 누적
                </p>
                <p className={styles.summaryValue}>
                  {stats.total_count.toLocaleString()}건
                </p>
                <p className={styles.summaryHint}>
                  {stats.from} ~ {stats.to}
                </p>
              </div>
            </div>

            <div className={styles.chartBox}>
              <h3 className={styles.chartTitle}>
                {activeUnit.label} 질문 추이
              </h3>
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
          </>
        )}
      </div>

      {/* === 하단: 리스트 그룹 (기간 검색 + 정렬) === */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionHead}>
          <div className={styles.sectionTitleGroup}>
            <h2 className={styles.sectionTitle}>질문 / 답변 목록</h2>
            <p className={styles.sectionHint}>
              아래 기간을 직접 지정해서 그 사이의 질문·답변을 살펴봅니다.
              위쪽 집계 단위와는 별개로 동작합니다.
            </p>
          </div>
          <div className={styles.sectionActions}>
            <a
              className={styles.exportBtn}
              href={buildQuestionsExportUrl({
                from: listFrom,
                to: listTo,
                sort,
              })}
              aria-label="현재 목록 조건으로 엑셀 내려받기"
            >
              ⬇ 엑셀 내려받기
            </a>
          </div>
        </div>

        <div className={styles.listFilters} role="toolbar" aria-label="목록 필터">
          <div className={styles.filterField}>
            <span className={styles.filterLabel}>기간 검색</span>
            <div className={styles.dateRange}>
              <input
                type="date"
                className={styles.dateInput}
                value={listFrom}
                max={listTo}
                onChange={(e) => handleFromChange(e.target.value)}
                aria-label="시작일"
              />
              <span className={styles.dateSeparator}>~</span>
              <input
                type="date"
                className={styles.dateInput}
                value={listTo}
                min={listFrom}
                max={daysAgoIso(0)}
                onChange={(e) => handleToChange(e.target.value)}
                aria-label="종료일"
              />
            </div>
          </div>
          <div className={styles.filterField}>
            <span className={styles.filterLabel}>빠른 선택</span>
            <div
              className={styles.quickRange}
              role="group"
              aria-label="빠른 기간 선택"
            >
              {QUICK_RANGES.map((r) => {
                const isActive =
                  listTo === daysAgoIso(0) &&
                  listFrom === daysAgoIso(r.days - 1);
                return (
                  <button
                    key={r.days}
                    type="button"
                    className={
                      isActive
                        ? styles.quickRangeBtnActive
                        : styles.quickRangeBtn
                    }
                    aria-pressed={isActive}
                    onClick={() => handleQuickRange(r.days)}
                  >
                    {r.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className={styles.filterField}>
            <span className={styles.filterLabel}>정렬</span>
            <div className={styles.unitToggle} role="group" aria-label="정렬">
              {SORTS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  className={
                    sort === s.value
                      ? styles.unitButtonActive
                      : styles.unitButton
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

        {listQuery.isLoading && (
          <p className={styles.statusMessage} role="status">
            질문 목록을 불러오는 중…
          </p>
        )}
        {!listQuery.isLoading && listQuery.error && (
          <section className={styles.errorBox} role="alert">
            <p>질문 목록을 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => listQuery.refetch()}
            >
              다시 시도
            </button>
          </section>
        )}

        {list && (
          <>
            <div className={styles.listMeta}>
              <span>
                <span className={styles.listMetaStrong}>
                  표시 중 질문 {list.total.toLocaleString()}건
                </span>{" "}
                · {listFrom} ~ {listTo}
              </span>
              {list.total > 0 && (
                <span>
                  {page} / {totalPages} 쪽
                </span>
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
                  {list.items.length === 0 ? (
                    <tr>
                      <td colSpan={5}>해당 조건의 질문이 없습니다.</td>
                    </tr>
                  ) : (
                    list.items.map((it) => {
                      const isActive = selectedId === it.qa_log_id;
                      return (
                        <tr
                          key={it.qa_log_id}
                          className={
                            isActive
                              ? `${styles.tableRow} ${styles.tableRowActive}`
                              : styles.tableRow
                          }
                          onClick={() => handleRowSelect(it.qa_log_id)}
                          aria-selected={isActive}
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              handleRowSelect(it.qa_log_id);
                            }
                          }}
                        >
                          <td>{formatDateTime(it.created_at)}</td>
                          <td>{it.email ?? "(비회원)"}</td>
                          <td>{segmentLabel(it.segment)}</td>
                          <td>
                            <div className={styles.qaCell}>
                              <p className={styles.qText}>
                                Q. {it.question_text}
                              </p>
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
                      );
                    })
                  )}
                </tbody>
              </table>
              {list.items.length > 0 && (
                <div className={styles.pagination}>
                  <button
                    type="button"
                    className={styles.pageBtn}
                    onClick={() => handlePageChange(Math.max(1, page - 1))}
                    disabled={page <= 1 || listQuery.isFetching}
                  >
                    ← 이전
                  </button>
                  <span className={styles.pageInfo}>
                    {page} / {totalPages} 쪽
                  </span>
                  <button
                    type="button"
                    className={styles.pageBtn}
                    onClick={() =>
                      handlePageChange(Math.min(totalPages, page + 1))
                    }
                    disabled={page >= totalPages || listQuery.isFetching}
                  >
                    다음 →
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {selectedId !== null && (
        <div
          className={styles.detailBackdrop}
          role="dialog"
          aria-modal="true"
          aria-label="질문 상세"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedId(null);
          }}
        >
          <div className={styles.detailDrawer}>
            <QuestionDetailPanel
              isLoading={detailQuery.isLoading}
              error={detailQuery.error}
              data={detailQuery.data}
              onClose={() => setSelectedId(null)}
              onRetry={() => detailQuery.refetch()}
            />
          </div>
        </div>
      )}
    </section>
  );
}

interface QuestionDetailPanelProps {
  isLoading: boolean;
  error: unknown;
  data: FeedbackDetail | undefined;
  onClose: () => void;
  onRetry: () => void;
}

function QuestionDetailPanel({
  isLoading,
  error,
  data,
  onClose,
  onRetry,
}: QuestionDetailPanelProps) {
  return (
    <div className={styles.detailPanel}>
      <header className={styles.detailHeader}>
        <h3 className={styles.detailTitle}>질문 상세</h3>
        <button
          type="button"
          className={styles.detailClose}
          onClick={onClose}
          aria-label="상세 패널 닫기"
        >
          ✕
        </button>
      </header>
      <div className={styles.detailBody}>
        {isLoading && (
          <p className={styles.detailFieldValueMuted} role="status">
            상세 내용을 불러오는 중…
          </p>
        )}
        {!isLoading && error != null && (
          <section className={styles.errorBox} role="alert">
            <p>상세 내용을 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={onRetry}
            >
              다시 시도
            </button>
          </section>
        )}
        {data && (
          <>
            <section className={styles.detailField}>
              <p className={styles.detailFieldLabel}>작성일시</p>
              <p className={styles.detailFieldValue}>
                {formatDateTime(data.created_at)}
              </p>
            </section>
            <section className={styles.detailField}>
              <p className={styles.detailFieldLabel}>질문 원문</p>
              <p className={styles.detailFieldValue}>
                {data.question_text || "(없음)"}
              </p>
            </section>
            <section className={styles.detailField}>
              <p className={styles.detailFieldLabel}>
                동의어 치환 쿼리 (검색에 실제로 쓰인 문장)
              </p>
              {data.normalized_query ? (
                <p className={styles.detailFieldValue}>
                  {data.normalized_query}
                </p>
              ) : (
                <p className={styles.detailFieldValueMuted}>
                  치환 없이 원문 그대로 검색되었습니다.
                </p>
              )}
            </section>
            <section className={styles.detailField}>
              <p className={styles.detailFieldLabel}>답변</p>
              {data.answer_text ? (
                <p className={styles.detailFieldValue}>{data.answer_text}</p>
              ) : (
                <p className={styles.detailFieldValueMuted}>
                  {statusFallback(data.status)}
                </p>
              )}
            </section>
            <section className={styles.detailField}>
              <p className={styles.detailFieldLabel}>
                검색된 문서 top-{data.retrieved_docs.length}
              </p>
              {data.retrieved_docs.length === 0 ? (
                <p className={styles.detailEmpty}>
                  (이 질문은 RAG 검색 없이 답변되었거나 기록이 없습니다)
                </p>
              ) : (
                <ol className={styles.detailDocList}>
                  {data.retrieved_docs.map((doc, idx) => (
                    <li key={idx} className={styles.detailDoc}>
                      <div className={styles.detailDocHead}>
                        <span className={styles.detailDocRank}>
                          #{idx + 1}
                        </span>
                        <p className={styles.detailDocMeta}>
                          {summarizeDocMetadata(doc.metadata)}
                        </p>
                      </div>
                      <p className={styles.detailDocContent}>
                        {doc.page_content || "(본문 없음)"}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function summarizeDocMetadata(meta: FeedbackRetrievedDoc["metadata"]): string {
  if (!meta || typeof meta !== "object") return "";
  const parts: string[] = [];
  const pick = (key: string): string | undefined => {
    const v = (meta as Record<string, unknown>)[key];
    if (v === undefined || v === null) return undefined;
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    return undefined;
  };
  const source = pick("source") ?? pick("file") ?? pick("doc_id");
  const page = pick("page") ?? pick("page_number");
  const section = pick("section") ?? pick("title") ?? pick("heading");
  if (source) parts.push(source);
  if (section) parts.push(section);
  if (page) parts.push(`p.${page}`);
  return parts.join(" · ");
}

function formatBucket(iso: string, unit: QuestionsUnit): string {
  const [y, m, d] = iso.split("-");
  if (unit === "year") return `${y}년`;
  if (unit === "month") return `${y}-${m}`;
  if (unit === "week") return `${m}-${d} 주`;
  return `${m}-${d}`;
}

function formatDateTime(iso: string): string {
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

function unitAverageLabel(unit: QuestionsUnit): string {
  if (unit === "year") return "연 평균";
  if (unit === "month") return "월 평균";
  if (unit === "week") return "주 평균";
  return "일 평균";
}

function currentPeriodLabel(unit: QuestionsUnit): string {
  if (unit === "year") return "올해 질문 수";
  if (unit === "month") return "이번 달 질문 수";
  if (unit === "week") return "이번 주 질문 수";
  return "오늘 질문 수";
}

function currentBucketCount(
  buckets: { bucket_start: string; count: number }[],
): number {
  if (buckets.length === 0) return 0;
  return buckets[buckets.length - 1].count;
}

function currentPeriodHint(
  buckets: { bucket_start: string; count: number }[],
  unit: QuestionsUnit,
): string {
  if (buckets.length === 0) return "최신 구간 자료가 없습니다";
  const last = buckets[buckets.length - 1];
  if (unit === "year") return `${last.bucket_start.slice(0, 4)}년 기준`;
  if (unit === "month") return `${last.bucket_start.slice(0, 7)} 기준`;
  if (unit === "week") return `${last.bucket_start} 주 시작 기준`;
  return `${last.bucket_start} 기준`;
}

function averagePerBucket(total: number, buckets: number): string {
  if (buckets <= 0) return "0";
  return Math.round(total / buckets).toLocaleString();
}

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
}
