"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchQaRecordYears,
  fetchQaRecords,
  fetchQaRecordsExport,
  buildQaRecordsExportUrl,
  type QaRecordSegment,
} from "@/features/admin-dashboard/api/analytics";
import styles from "./page.module.css";

// 가입유형 드롭다운 선택지 — 전체 + 3종.
const SEGMENT_OPTIONS: { value: QaRecordSegment | ""; label: string }[] = [
  { value: "", label: "전체" },
  { value: "doctor", label: "치과의사" },
  { value: "hygienist", label: "치과위생사" },
  { value: "student_other", label: "학생/기타" },
];

const PER_PAGE = 20;

export default function QaRecordsAnalyticsPage() {
  // 필터 (조회 버튼을 눌러야 실제 질의에 반영되는 "입력" 상태)
  const [segmentInput, setSegmentInput] = useState<QaRecordSegment | "">("");
  const [yearInput, setYearInput] = useState<string>(""); // "" = 전체
  const [fromInput, setFromInput] = useState<string>(() => daysAgoIso(29));
  const [toInput, setToInput] = useState<string>(() => daysAgoIso(0));

  // 실제 적용된 필터 (조회 버튼 클릭 시 커밋)
  const [applied, setApplied] = useState<{
    segment: QaRecordSegment | "";
    year: string;
    from: string;
    to: string;
  }>({
    segment: "",
    year: "",
    from: daysAgoIso(29),
    to: daysAgoIso(0),
  });

  const [page, setPage] = useState(1);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // 선택한 가입유형이 실제 가진 연차만 동적 로딩.
  const yearsQuery = useQuery({
    queryKey: ["admin", "analytics", "qa-records", "years", segmentInput],
    queryFn: () =>
      fetchQaRecordYears(
        segmentInput ? { segment: segmentInput } : {},
      ),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // 가입유형을 바꾸면 기존 연차 선택이 새 목록에 없을 수 있으므로 초기화.
  useEffect(() => {
    setYearInput("");
  }, [segmentInput]);

  const listQuery = useQuery({
    queryKey: ["admin", "analytics", "qa-records", "list", applied, page],
    queryFn: () =>
      fetchQaRecords({
        segment: applied.segment || undefined,
        year: applied.year === "" ? undefined : Number(applied.year),
        from: applied.from,
        to: applied.to,
        page,
        per_page: PER_PAGE,
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const list = listQuery.data;
  const totalPages = list ? Math.max(1, Math.ceil(list.total / PER_PAGE)) : 1;

  function handleSearch() {
    setApplied({
      segment: segmentInput,
      year: yearInput,
      from: fromInput,
      to: toInput,
    });
    setPage(1);
  }

  function handlePageChange(next: number) {
    setPage(next);
  }

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await fetchQaRecordsExport({
        segment: applied.segment || undefined,
        year: applied.year === "" ? undefined : Number(applied.year),
        from: applied.from,
        to: applied.to,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : "엑셀 다운로드에 실패했습니다.",
      );
    } finally {
      setDownloading(false);
    }
  }

  const years = yearsQuery.data?.years ?? [];

  return (
    <section className={styles.page} aria-labelledby="qa-records-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="qa-records-title" className={styles.title}>
            가입유형별·연차별 질문기록
          </h1>
          <p className={styles.caption}>
            가입유형과 연차, 기간을 지정해 해당 가입자들의 질문 내용을 한 번에
            조회합니다. 연차 선택지는 고른 가입유형이 실제로 가진 연차만
            나타납니다. 표로 확인하거나 엑셀로 내려받을 수 있습니다.
          </p>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.downloadBtn}
            onClick={handleDownload}
            disabled={downloading}
            data-export-url={buildQaRecordsExportUrl({
              segment: applied.segment || undefined,
              year: applied.year === "" ? undefined : Number(applied.year),
              from: applied.from,
              to: applied.to,
            })}
            aria-label="현재 조회 조건으로 엑셀 내려받기"
          >
            ⬇ 엑셀 다운로드
          </button>
        </div>
      </header>

      {downloadError && (
        <p className={styles.downloadError} role="alert">
          {downloadError}
        </p>
      )}

      <div className={styles.filterCard} role="toolbar" aria-label="조회 조건">
        <div className={styles.filterField}>
          <label className={styles.filterLabel} htmlFor="qa-segment">
            가입유형
          </label>
          <select
            id="qa-segment"
            className={styles.select}
            value={segmentInput}
            onChange={(e) =>
              setSegmentInput(e.target.value as QaRecordSegment | "")
            }
          >
            {SEGMENT_OPTIONS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.filterField}>
          <label className={styles.filterLabel} htmlFor="qa-year">
            연차
          </label>
          <select
            id="qa-year"
            className={styles.select}
            value={yearInput}
            onChange={(e) => setYearInput(e.target.value)}
            disabled={yearsQuery.isLoading}
          >
            <option value="">전체</option>
            {years.map((y) => (
              <option key={y} value={String(y)}>
                {y}년차
              </option>
            ))}
          </select>
          {yearsQuery.isLoading && (
            <span className={styles.fieldHint}>연차 불러오는 중…</span>
          )}
          {!yearsQuery.isLoading && years.length === 0 && (
            <span className={styles.fieldHint}>
              해당 유형에 연차 정보가 없습니다.
            </span>
          )}
        </div>

        <div className={styles.filterField}>
          <span className={styles.filterLabel}>기간</span>
          <div className={styles.dateRange}>
            <input
              type="date"
              className={styles.dateInput}
              value={fromInput}
              max={toInput}
              onChange={(e) => setFromInput(e.target.value)}
              aria-label="시작일"
            />
            <span className={styles.dateSeparator}>~</span>
            <input
              type="date"
              className={styles.dateInput}
              value={toInput}
              min={fromInput}
              onChange={(e) => setToInput(e.target.value)}
              aria-label="종료일"
            />
          </div>
        </div>

        <div className={styles.filterField}>
          <span className={styles.filterLabel}>&nbsp;</span>
          <button
            type="button"
            className={styles.searchBtn}
            onClick={handleSearch}
            disabled={listQuery.isFetching}
          >
            조회
          </button>
        </div>
      </div>

      {listQuery.isLoading && (
        <p className={styles.statusMessage} role="status">
          질문기록을 불러오는 중…
        </p>
      )}

      {!listQuery.isLoading && listQuery.error && (
        <section className={styles.errorBox} role="alert">
          <p>질문기록을 불러오지 못했습니다.</p>
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
                총 {list.total.toLocaleString()}건
              </span>{" "}
              · {segmentAppliedLabel(applied.segment)} ·{" "}
              {applied.year === "" ? "전체 연차" : `${applied.year}년차`} ·{" "}
              {applied.from} ~ {applied.to}
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
                  <th className={styles.numCell}>연차</th>
                  <th>질문</th>
                </tr>
              </thead>
              <tbody>
                {list.items.length === 0 ? (
                  <tr>
                    <td colSpan={5} className={styles.emptyRow}>
                      해당 조건의 질문기록이 없습니다.
                    </td>
                  </tr>
                ) : (
                  list.items.map((it) => (
                    <tr key={it.qa_log_id}>
                      <td>{formatDateTime(it.created_at_kst)}</td>
                      <td>{it.email_masked || "(비회원)"}</td>
                      <td>{it.segment_label || "—"}</td>
                      <td className={styles.numCell}>
                        {it.years_of_experience != null
                          ? `${it.years_of_experience}년차`
                          : "—"}
                      </td>
                      <td>
                        <p className={styles.qText}>{it.question_text}</p>
                      </td>
                    </tr>
                  ))
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
    </section>
  );
}

function segmentAppliedLabel(seg: QaRecordSegment | ""): string {
  if (seg === "doctor") return "치과의사";
  if (seg === "hygienist") return "치과위생사";
  if (seg === "student_other") return "학생/기타";
  return "전체 유형";
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
