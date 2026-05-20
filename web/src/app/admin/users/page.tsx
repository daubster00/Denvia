"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  type SearchFilters,
  SearchFilterBar,
} from "@/features/admin-users/components/SearchFilterBar";
import { UserSearchTable } from "@/features/admin-users/components/UserSearchTable";
import { useUsersSearch } from "@/features/admin-users/hooks/useUsersSearch";
import styles from "./page.module.css";

const DEFAULT_FILTERS: SearchFilters = {
  q: "",
  segment: null,
  subscription_status: null,
  blocked: null,
  created_from: "",
  created_to: "",
};

const PER_PAGE = 20;

export default function AdminUsersPage() {
  const router = useRouter();

  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
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
