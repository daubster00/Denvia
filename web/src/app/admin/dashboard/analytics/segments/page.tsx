"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  buildSegmentsExportUrl,
  fetchSegments,
  fetchSegmentsExport,
  type ExperienceRow,
  type SegmentKey,
  type SegmentsResponse,
} from "@/features/admin-dashboard/api/analytics";
import { DashboardChart } from "@/features/admin-dashboard/components/DashboardChart";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import styles from "./page.module.css";

const SEGMENT_LABELS: Record<SegmentKey, string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

export default function SegmentsAnalyticsPage() {
  const router = useRouter();
  const [includeWithdrawn, setIncludeWithdrawn] = useState(false);
  const [includeBlocked, setIncludeBlocked] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: [
      "admin",
      "analytics",
      "segments",
      { includeWithdrawn, includeBlocked },
    ],
    queryFn: () =>
      fetchSegments({
        include_withdrawn: includeWithdrawn,
        include_blocked: includeBlocked,
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const handleKpiClick = (segment: SegmentKey) => {
    router.push(`/admin/users?segment=${segment}`);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await fetchSegmentsExport({
        include_withdrawn: includeWithdrawn,
        include_blocked: includeBlocked,
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
  };

  const totalSum = data?.by_segment.reduce((s, r) => s + r.count, 0) ?? 0;

  return (
    <section className={styles.page} aria-labelledby="segments-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="segments-title" className={styles.title}>
            가입유형 통계
          </h1>
          <p className={styles.caption}>
            치과의사·치과위생사·학생/기타 분포와 연차별 히스토그램을 확인합니다.
          </p>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={() => refetch()}
            aria-label="가입유형 통계 새로고침"
            disabled={isFetching}
          >
            ↻ 새로고침
          </button>
          <button
            type="button"
            className={styles.downloadBtn}
            onClick={handleDownload}
            disabled={downloading}
            data-export-url={buildSegmentsExportUrl({
              include_withdrawn: includeWithdrawn,
              include_blocked: includeBlocked,
            })}
          >
            📥 엑셀 다운로드
          </button>
        </div>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="집계 필터">
        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={includeWithdrawn}
            onChange={(e) => setIncludeWithdrawn(e.target.checked)}
          />
          <span>탈퇴자 포함</span>
        </label>
        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={includeBlocked}
            onChange={(e) => setIncludeBlocked(e.target.checked)}
          />
          <span>차단자 포함</span>
        </label>
      </div>

      {downloadError && (
        <p className={styles.downloadError} role="alert">
          {downloadError}
        </p>
      )}

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          가입유형 데이터를 불러오는 중…
        </p>
      )}

      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>가입유형 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && totalSum === 0 && (
        <p className={styles.emptyState} role="status">
          사용자 데이터가 없습니다.
        </p>
      )}

      {data && totalSum > 0 && (
        <>
          <div className={styles.kpiRow}>
            {data.by_segment.map((row) => (
              <KPICard
                key={row.segment}
                label={SEGMENT_LABELS[row.segment]}
                value={`${row.count.toLocaleString()}명`}
                onClick={() => handleKpiClick(row.segment)}
              />
            ))}
          </div>

          <section className={styles.chartBlock} aria-labelledby="seg-bar-title">
            <h2 id="seg-bar-title" className={styles.sectionTitle}>
              가입유형별 분포
            </h2>
            <DashboardChart
              variant="bar"
              data={data.by_segment.map((r) => ({
                name: SEGMENT_LABELS[r.segment],
                count: r.count,
                active_count: r.active_count,
                pro_count: r.pro_count,
              }))}
              series={[
                { key: "count", label: "전체", tone: "brand" },
                { key: "active_count", label: "활성", tone: "success" },
                { key: "pro_count", label: "Pro", tone: "warning" },
              ]}
              ariaLabel="가입유형 분포 차트"
            />
          </section>

          <section className={styles.chartBlock} aria-labelledby="seg-exp-title">
            <h2 id="seg-exp-title" className={styles.sectionTitle}>
              연차별 인원수 (의사·위생사)
            </h2>
            <div className={styles.histGrid}>
              <ExperienceColumn
                title="치과의사"
                rows={data.by_experience.filter((r) => r.segment === "doctor")}
              />
              <ExperienceColumn
                title="치과위생사"
                rows={data.by_experience.filter(
                  (r) => r.segment === "hygienist",
                )}
              />
            </div>
            <p className={styles.experienceNote}>
              학생·기타 가입유형은 연차 정보가 없습니다.
            </p>
          </section>
        </>
      )}
    </section>
  );
}

function ExperienceColumn({
  title,
  rows,
}: {
  title: string;
  rows: ExperienceRow[];
}) {
  return (
    <div className={styles.histColumn}>
      <h3 className={styles.histTitle}>{title}</h3>
      <DashboardChart
        variant="bar"
        data={rows.map((r) => ({ name: r.years_bucket, count: r.count }))}
        series={[{ key: "count", label: "인원수", tone: "brand" }]}
        ariaLabel={`${title} 연차 분포`}
      />
    </div>
  );
}
