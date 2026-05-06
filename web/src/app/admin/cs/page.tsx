"use client";

import { useState } from "react";
import type { InquiryStatus } from "@/features/admin-support/api/inquiries";
import { InquiryDetailDrawer } from "@/features/admin-support/components/InquiryDetailDrawer";
import { InquiryListTable } from "@/features/admin-support/components/InquiryListTable";
import { StatusFilterBar } from "@/features/admin-support/components/StatusFilterBar";
import { useInquiriesSearch } from "@/features/admin-support/hooks/useInquiriesSearch";
import { useInquiryDetail } from "@/features/admin-support/hooks/useInquiryDetail";
import styles from "./page.module.css";

const PER_PAGE = 20;

export default function CsPage() {
  const [status, setStatus] = useState<InquiryStatus | null>(null);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const list = useInquiriesSearch({
    status: status ?? undefined,
    page,
    per_page: PER_PAGE,
  });
  const detail = useInquiryDetail(selectedId);

  function handleStatusChange(next: InquiryStatus | null) {
    setStatus(next);
    setPage(1);
  }

  return (
    <section className={styles.page} aria-labelledby="admin-cs-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-cs-title" className={styles.title}>
            CS
          </h1>
          <p className={styles.caption}>
            고객 문의를 조회하고 답변을 등록합니다. 답변은 사용자 알림함으로 즉시 발송됩니다.
          </p>
        </div>
      </header>

      <StatusFilterBar
        value={status}
        onChange={handleStatusChange}
        onRefresh={() => list.refetch()}
        isFetching={list.isFetching}
      />

      <InquiryListTable
        data={list.data}
        isLoading={list.isLoading}
        isError={list.isError}
        page={page}
        perPage={PER_PAGE}
        onPageChange={setPage}
        onSelect={(item) => setSelectedId(item.id)}
        onResetFilters={() => handleStatusChange(null)}
        onRetry={() => list.refetch()}
      />

      <InquiryDetailDrawer
        open={selectedId !== null}
        detail={detail.data}
        isLoading={detail.isLoading}
        isError={detail.isError}
        onClose={() => setSelectedId(null)}
        onRetry={() => detail.refetch()}
      />
    </section>
  );
}
