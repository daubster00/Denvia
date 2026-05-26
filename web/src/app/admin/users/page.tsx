"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  type SearchFilters,
  SearchFilterBar,
} from "@/features/admin-users/components/SearchFilterBar";
import { UserSearchTable } from "@/features/admin-users/components/UserSearchTable";
import { useUsersSearch } from "@/features/admin-users/hooks/useUsersSearch";
import type {
  Segment,
  SubscriptionStatus,
} from "@/features/admin-users/api/users";
import styles from "./page.module.css";

const DEFAULT_FILTERS: SearchFilters = {
  q: "",
  segment: null,
  subscription_status: null,
  blocked: null,
  withdrawn: null,
  created_from: "",
  created_to: "",
};

const PER_PAGE = 20;

const VALID_SEGMENTS: Segment[] = ["doctor", "hygienist", "student_other"];
const VALID_STATUSES: SubscriptionStatus[] = ["free", "pro", "blocked"];

function parseBool(raw: string | null): boolean | null {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return null;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // 대시보드 구독 현황의 KPI/legend 클릭 진입을 위해 URL 파라미터를 초기 필터로 시드한다.
  // useMemo는 마운트 시 1회만 — 이후 SearchFilterBar 조작은 setFilters로만 진행.
  const initialFilters = useMemo<SearchFilters>(() => {
    const segmentRaw = searchParams.get("segment");
    const statusRaw = searchParams.get("subscription_status");
    return {
      q: searchParams.get("q") ?? "",
      segment:
        segmentRaw && (VALID_SEGMENTS as string[]).includes(segmentRaw)
          ? (segmentRaw as Segment)
          : null,
      subscription_status:
        statusRaw && (VALID_STATUSES as string[]).includes(statusRaw)
          ? (statusRaw as SubscriptionStatus)
          : null,
      blocked: parseBool(searchParams.get("blocked")),
      withdrawn: parseBool(searchParams.get("withdrawn")),
      created_from: searchParams.get("created_from") ?? "",
      created_to: searchParams.get("created_to") ?? "",
    };
    // 마운트 시 1회 — searchParams 변경 시 재시드하지 않음(사용자 조작 우선).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [filters, setFilters] = useState<SearchFilters>(initialFilters);
  const [page, setPage] = useState(1);

  const dateRangeValid =
    !filters.created_from ||
    !filters.created_to ||
    filters.created_from <= filters.created_to;

  const search = useUsersSearch({
    q: filters.q || undefined,
    segment: filters.segment ?? undefined,
    subscription_status: filters.subscription_status ?? undefined,
    blocked: filters.blocked ?? undefined,
    withdrawn: filters.withdrawn ?? undefined,
    created_from: dateRangeValid && filters.created_from ? filters.created_from : undefined,
    created_to: dateRangeValid && filters.created_to ? filters.created_to : undefined,
    page,
    per_page: PER_PAGE,
  });

  function handleFilterChange(next: SearchFilters) {
    setFilters(next);
    setPage(1); // 필터 변경 시 1페이지로 리셋
  }

  function handleResetFilters() {
    setFilters(DEFAULT_FILTERS);
    setPage(1);
  }

  return (
    <section className={styles.page} aria-labelledby="admin-users-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-users-title" className={styles.title}>
            고객 관리
          </h1>
          <p className={styles.caption}>
            이메일·휴대폰·카드 뒷4자리로 통합 검색하여 사용자 상세를 확인합니다.
          </p>
        </div>
      </header>

      <SearchFilterBar
        value={filters}
        onChange={handleFilterChange}
        onReset={handleResetFilters}
        onRefresh={() => search.refetch()}
        isFetching={search.isFetching}
      />

      <UserSearchTable
        data={search.data}
        isLoading={search.isLoading}
        isError={search.isError}
        page={page}
        perPage={PER_PAGE}
        onPageChange={setPage}
        onSelectUser={(item) => router.push(`/admin/users/${item.user_id}`)}
        onResetFilters={handleResetFilters}
        onRetry={() => search.refetch()}
      />
    </section>
  );
}
