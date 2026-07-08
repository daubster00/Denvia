"use client";

import {
  type KeyboardEvent,
  useMemo,
  useState,
} from "react";
import type {
  UserSearchItem,
  UserSearchListResponse,
} from "@/features/admin-users/api/users";
import {
  formatSegment,
  formatSubscriptionStatus,
} from "@/features/admin-users/labels";
import { AdminDMDialog } from "./AdminDMDialog";
import styles from "./UserSearchTable.module.css";

interface Props {
  data: UserSearchListResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  page: number;
  perPage: number;
  onPageChange: (next: number) => void;
  onSelectUser: (user: UserSearchItem) => void;
  onResetFilters: () => void;
  onRetry: () => void;
}

interface DMTarget {
  userId: number;
  email: string;
}

const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function formatDate(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_FORMAT.format(new Date(value));
  } catch {
    return value;
  }
}

export function UserSearchTable({
  data,
  isLoading,
  isError,
  page,
  perPage,
  onPageChange,
  onSelectUser,
  onResetFilters,
  onRetry,
}: Props) {
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = useMemo(
    () => (total === 0 ? 1 : Math.ceil(total / perPage)),
    [total, perPage],
  );

  const [dmTarget, setDmTarget] = useState<DMTarget | null>(null);

  function handleRowKey(event: KeyboardEvent<HTMLTableRowElement>, item: UserSearchItem) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelectUser(item);
    }
  }

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        <p className={styles.errorText}>
          사용자 데이터를 불러오는 중 문제가 발생했습니다.
        </p>
        <button type="button" className={styles.retryButton} onClick={onRetry}>
          다시 시도
        </button>
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className={styles.emptyBox} role="status">
        <p className={styles.emptyTitle}>
          검색 조건에 해당하는 사용자가 없습니다
        </p>
        <p className={styles.emptyHint}>필터를 조정하거나 검색어를 변경해보세요</p>
        <button
          type="button"
          className={styles.resetButton}
          onClick={onResetFilters}
        >
          검색 조건 초기화
        </button>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.tableScroll}>
      <table
        className={styles.table}
        role="table"
        aria-rowcount={total}
        aria-busy={isLoading}
      >
        <thead className={styles.thead}>
          <tr>
            <th scope="col">이메일</th>
            <th scope="col">휴대폰</th>
            <th scope="col">가입유형</th>
            <th scope="col">구독 상태</th>
            <th scope="col">카드</th>
            <th scope="col">가입일</th>
            <th scope="col" aria-label="작업"></th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const isWithdrawn = item.withdrawn_at !== null;
            const rowClass = isWithdrawn
              ? `${styles.row} ${styles.rowWithdrawn}`
              : styles.row;
            return (
              <tr
                key={item.user_id}
                className={rowClass}
                role="row"
                tabIndex={0}
                onClick={() => onSelectUser(item)}
                onKeyDown={(e) => handleRowKey(e, item)}
                data-testid={`user-row-${item.user_id}`}
                data-withdrawn={isWithdrawn ? "true" : "false"}
              >
                <td>{item.email}</td>
                <td>{item.phone ?? "—"}</td>
                <td>{formatSegment(item.segment)}</td>
                <td>
                  <span
                    className={
                      item.subscription_status === "blocked"
                        ? styles.badgeBlocked
                        : item.subscription_status === "pro"
                          ? styles.badgePro
                          : styles.badgeFree
                    }
                  >
                    {formatSubscriptionStatus(item.subscription_status)}
                  </span>
                  {isWithdrawn ? (
                    <span className={styles.badgeWithdrawn}>탈퇴</span>
                  ) : null}
                </td>
                <td>
                  {item.card_last4
                    ? `${item.card_company ?? ""} ${item.card_last4}`
                    : "—"}
                </td>
                <td>{formatDate(item.created_at)}</td>
                <td className={styles.actionCell}>
                  <button
                    type="button"
                    className={styles.dmButton}
                    onClick={(e) => {
                      e.stopPropagation();
                      setDmTarget({ userId: item.user_id, email: item.email });
                    }}
                    disabled={isWithdrawn}
                    aria-label={`${item.email}에게 쪽지 보내기`}
                    title={
                      isWithdrawn
                        ? "탈퇴한 사용자에게는 보낼 수 없습니다"
                        : "쪽지 보내기"
                    }
                  >
                    쪽지
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      <AdminDMDialog
        open={dmTarget !== null}
        targetUserId={dmTarget?.userId ?? 0}
        targetEmail={dmTarget?.email ?? ""}
        onClose={() => setDmTarget(null)}
        onSent={() => {
          /* 쪽지 발송 성공 토스트는 차기 작업 — 일단 모달 닫힘으로 충분 */
        }}
      />

      <nav className={styles.pagination} aria-label="페이지 네비게이션">
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1 || isLoading}
          aria-label="이전 페이지"
        >
          이전
        </button>
        <span className={styles.pageLabel} aria-live="polite">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages || isLoading}
          aria-label="다음 페이지"
        >
          다음
        </button>
      </nav>
    </div>
  );
}
