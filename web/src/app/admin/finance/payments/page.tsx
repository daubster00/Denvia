"use client";

import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { IconDownload } from "@wanteddev/wds-icon";
import {
  buildPaymentEventsExportUrl,
  type PaymentEventItem,
} from "@/features/admin-finance/api/payments";
import { usePaymentEvents } from "@/features/admin-finance/hooks/usePaymentEvents";
import { AdminLogTimeline } from "@/features/admin-finance/components/AdminLogTimeline";
import { PaymentEventDetailDrawer } from "@/features/admin-finance/components/PaymentEventDetailDrawer";
import {
  FinanceFilterBar,
  type FinanceFilterValues,
} from "@/features/admin-finance/components/FinanceFilterBar";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import styles from "./page.module.css";

const PER_PAGE_OPTIONS = [50, 100, 200] as const;

export default function PaymentsTimelinePage() {
  const [filters, setFilters] = useState<FinanceFilterValues>({
    from: "",
    to: "",
    statusIn: [],
    errorCode: "",
    userId: undefined,
  });
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState<number>(50);
  const [drawerEventId, setDrawerEventId] = useState<number | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const qc = useQueryClient();

  const queryParams = useMemo(
    () => ({
      from: filters.from || undefined,
      to: filters.to || undefined,
      status_in: filters.statusIn.length ? filters.statusIn.join(",") : undefined,
      provider_error_code: filters.errorCode || undefined,
      user_id: filters.userId,
      page,
      per_page: perPage,
    }),
    [filters, page, perPage],
  );

  const { data, error, refetch, isLoading, isFetching } = usePaymentEvents(queryParams);

  // 자동완성 보조 — 현재 페이지에서 distinct error_code 추출
  const errorCodeOptions = useMemo(
    () =>
      Array.from(
        new Set(
          (data?.items ?? [])
            .map((it) => it.provider_error_code)
            .filter((c): c is string => Boolean(c)),
        ),
      ),
    [data?.items],
  );

  const handleFilterChange = (next: FinanceFilterValues) => {
    setFilters(next);
    setPage(1);
  };

  const handleExport = useCallback(() => {
    setIsExporting(true);
    try {
      const url = buildPaymentEventsExportUrl(queryParams);
      const iframe = document.createElement("iframe");
      iframe.src = url;
      iframe.hidden = true;
      iframe.title = "payment-events-export";
      document.body.appendChild(iframe);
      window.setTimeout(() => iframe.remove(), 60_000);
    } finally {
      window.setTimeout(() => setIsExporting(false), 700);
    }
  }, [queryParams]);

  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / perPage));

  return (
    <section className={styles.page} aria-labelledby="payments-title">
      <header className={styles.header}>
        <h1 id="payments-title" className={styles.title}>
          결제 기록
        </h1>
        <p className={styles.caption}>
          결제 성공·실패·환불·PG 에러 이벤트를 통합 타임라인으로 조회합니다.
        </p>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() =>
            qc.invalidateQueries({
              queryKey: ["admin", "finance", "payment-events"],
            })
          }
          disabled={isFetching}
          aria-label="새로고침"
        >
          {isFetching ? "↻ 갱신 중" : "↻ 새로고침"}
        </button>
      </header>

      <FinanceFilterBar
        from={filters.from}
        to={filters.to}
        statusIn={filters.statusIn}
        errorCode={filters.errorCode}
        userId={filters.userId}
        onChange={handleFilterChange}
        errorCodeOptions={errorCodeOptions}
      />

      {data?.error_code_summary && (
        <div className={styles.kpiRow}>
          <KPICard
            label="해당 에러 총 건수"
            value={`${data.error_code_summary.event_count.toLocaleString("ko-KR")}건`}
          />
          <KPICard
            label="영향받은 사용자 수"
            value={`${data.error_code_summary.affected_user_count.toLocaleString("ko-KR")}명`}
          />
        </div>
      )}

      <div className={styles.actionBar}>
        <p className={styles.totalCount}>
          전체 {total.toLocaleString("ko-KR")}건
        </p>
        <button
          type="button"
          className={styles.exportBtn}
          onClick={handleExport}
          disabled={isExporting || isLoading}
        >
          <IconDownload aria-hidden="true" />
          <span>{isExporting ? "내보내는 중…" : "엑셀 내보내기"}</span>
        </button>
      </div>

      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>결제 이벤트를 불러오지 못했습니다.</p>
          <button type="button" onClick={() => refetch()}>
            다시 시도
          </button>
        </section>
      )}

      <AdminLogTimeline
        events={data?.items ?? []}
        onRowClick={(e: PaymentEventItem) => setDrawerEventId(e.event_id)}
        groupByDate
        isLoading={isLoading}
        emptyMessage="이 기간에 결제 이벤트가 없습니다."
      />

      <nav className={styles.pagination} aria-label="페이지네이션">
        <label className={styles.perPageLabel}>
          페이지당
          <select
            value={perPage}
            onChange={(e) => {
              setPerPage(Number(e.target.value));
              setPage(1);
            }}
          >
            {PER_PAGE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}건
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
        >
          이전
        </button>
        <span className={styles.pageInfo}>
          {page} / {lastPage}
        </span>
        <button
          type="button"
          onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
          disabled={page >= lastPage}
        >
          다음
        </button>
      </nav>

      {drawerEventId !== null && (
        <PaymentEventDetailDrawer
          eventId={drawerEventId}
          onClose={() => setDrawerEventId(null)}
        />
      )}
    </section>
  );
}
