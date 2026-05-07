"use client";

import { useState } from "react";
import type { InquiryStatus } from "@/features/admin-support/api/inquiries";
import { useInquiriesSearch } from "@/features/admin-support/hooks/useInquiriesSearch";
import { useInquiryDetail } from "@/features/admin-support/hooks/useInquiryDetail";
import { InquiryDetailDrawer } from "./InquiryDetailDrawer";
import { InquiryListTable } from "./InquiryListTable";
import { StatusFilterBar } from "./StatusFilterBar";

const PER_PAGE = 50;

export function InquiriesTabPanel() {
  const [statusIn, setStatusIn] = useState<Set<InquiryStatus>>(new Set());
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const list = useInquiriesSearch({
    status_in: statusIn.size > 0 ? Array.from(statusIn) : undefined,
    q: q.trim().length > 0 ? q.trim() : undefined,
    from: from || undefined,
    to: to || undefined,
    page,
    per_page: PER_PAGE,
  });
  const detail = useInquiryDetail(selectedId);

  function toggleStatus(status: InquiryStatus) {
    setStatusIn((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
    setPage(1);
  }

  function resetStatus() {
    setStatusIn(new Set());
    setPage(1);
  }

  function resetAllFilters() {
    setStatusIn(new Set());
    setQ("");
    setFrom("");
    setTo("");
    setPage(1);
  }

  return (
    <>
      <StatusFilterBar
        statusIn={statusIn}
        q={q}
        from={from}
        to={to}
        onStatusToggle={toggleStatus}
        onStatusReset={resetStatus}
        onQChange={(next) => {
          setQ(next);
          setPage(1);
        }}
        onFromChange={(next) => {
          setFrom(next);
          setPage(1);
        }}
        onToChange={(next) => {
          setTo(next);
          setPage(1);
        }}
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
        onResetFilters={resetAllFilters}
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
    </>
  );
}
