"use client";

import { useMemo, useState } from "react";
import type {
  AnomalyEventItem,
  AnomalyListResponse,
} from "@/features/admin-anomaly/api/anomaly";
import { formatAnomalyType } from "@/features/admin-users/labels";
import {
  useAddWatch,
  useRemoveWatch,
} from "@/features/admin-anomaly/hooks/useWatchToggle";
import { useMarkReviewed } from "@/features/admin-anomaly/hooks/useMarkReviewed";
import { AdminDMDialog } from "@/features/admin-users/components/AdminDMDialog";
import { AnomalyStatusBadge } from "./AnomalyStatusBadge";
import styles from "./AnomalyTable.module.css";

interface DMTarget {
  userId: number;
  email: string;
}

interface Props {
  data: AnomalyListResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  page: number;
  perPage: number;
  onPageChange: (next: number) => void;
  onShowDetail: (anomaly: AnomalyEventItem) => void;
  onRetry: () => void;
}

const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_FORMAT.format(new Date(value));
  } catch {
    return value;
  }
}

/**
 * 비밀번호 다회 오류(login_brute_force) 의 단계별 행 클래스를 결정.
 * - stage 1 (3회 실패 → 10분 락) → 노란색
 * - stage 2 (락 해제 후 재시도 또 실패) → 빨간색
 * 그 외 타입은 기본 색상.
 */
function rowSeverityClass(item: AnomalyEventItem): string {
  if (item.type !== "login_brute_force") return "";
  const stage = (item.details as { stage?: unknown })?.stage;
  if (stage === 2) return styles.rowSeverityRed;
  if (stage === 1) return styles.rowSeverityYellow;
  return "";
}

export function AnomalyTable({
  data,
  isLoading,
  isError,
  page,
  perPage,
  onPageChange,
  onShowDetail,
  onRetry,
}: Props) {
  const addWatch = useAddWatch();
  const removeWatch = useRemoveWatch();
  const markReviewed = useMarkReviewed();
  const watchPending = addWatch.isPending || removeWatch.isPending;
  const [dmTarget, setDmTarget] = useState<DMTarget | null>(null);

  function handleShowDetail(item: AnomalyEventItem) {
    // 상세보기 클릭 시 'new' 상태인 항목은 곧바로 검토완료로 전이.
    // 'reviewed'/'actioned'/'unblocked' 는 그대로 두고 드로어만 연다.
    if (item.status === "new") {
      markReviewed.mutate(item.id);
    }
    onShowDetail(item);
  }

  function handleToggleWatch(item: AnomalyEventItem) {
    if (item.target_user_id === null) return;
    if (item.is_watched) {
      removeWatch.mutate({ userId: item.target_user_id });
    } else {
      addWatch.mutate({ anomalyId: item.id });
    }
  }

  function handleOpenDM(item: AnomalyEventItem) {
    if (item.target_user_id === null) return;
    setDmTarget({
      userId: item.target_user_id,
      email: item.target_user_email_masked ?? `#${item.target_user_id}`,
    });
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = useMemo(
    () => (total === 0 ? 1 : Math.ceil(total / perPage)),
    [total, perPage],
  );

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        <p className={styles.errorText}>
          이상 이벤트 데이터를 불러오는 중 문제가 발생했습니다.
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
        <p className={styles.emptyTitle}>이상 이벤트가 없습니다.</p>
        <p className={styles.emptyHint}>
          분류 탭이나 상태 필터를 변경해보세요.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <table
        className={styles.table}
        role="table"
        aria-rowcount={total}
        aria-busy={isLoading}
      >
        <thead className={styles.thead}>
          <tr>
            <th scope="col">발생일시</th>
            <th scope="col">분류</th>
            <th scope="col">대상 사용자</th>
            <th scope="col">IP</th>
            <th scope="col">상태</th>
            <th scope="col">상세</th>
            <th scope="col" aria-label="주의 계정">주의</th>
            <th scope="col" aria-label="쪽지 보내기">쪽지</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const userCell = item.target_user_id ? (
              <a
                href={`/admin/users/${item.target_user_id}`}
                className={styles.userLink}
                onClick={(e) => e.stopPropagation()}
              >
                {item.target_user_email_masked ?? `#${item.target_user_id}`}
              </a>
            ) : (
              "—"
            );

            const severityClass = rowSeverityClass(item);
            return (
              <tr
                key={item.id}
                className={
                  severityClass ? `${styles.row} ${severityClass}` : styles.row
                }
                data-testid={`anomaly-row-${item.id}`}
              >
                <td>{formatDateTime(item.created_at)}</td>
                <td>
                  {formatAnomalyType(item.type)}
                  {item.occurrence_count > 1 ? (
                    <span
                      className={styles.countBadge}
                      data-testid={`anomaly-count-${item.id}`}
                    >
                      {item.occurrence_count}회
                    </span>
                  ) : null}
                </td>
                <td>{userCell}</td>
                <td>{item.ip ?? "—"}</td>
                <td>
                  <AnomalyStatusBadge
                    status={item.status}
                    blockedNow={item.user_blocked_now}
                    throttledNow={item.user_auto_throttled_now}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className={styles.detailButton}
                    onClick={() => handleShowDetail(item)}
                    data-testid={`anomaly-detail-${item.id}`}
                  >
                    상세보기
                  </button>
                </td>
                <td>
                  <button
                    type="button"
                    className={
                      item.is_watched
                        ? `${styles.starButton} ${styles.starIcon} ${styles.starActive}`
                        : `${styles.starButton} ${styles.starIcon}`
                    }
                    aria-pressed={item.is_watched}
                    aria-label={
                      item.is_watched ? "주의 계정 해제" : "주의 계정 등록"
                    }
                    title={
                      item.target_user_id === null
                        ? "대상 사용자 미식별 — 등록 불가"
                        : item.is_watched
                          ? "주의 계정 해제"
                          : "주의 계정 등록"
                    }
                    onClick={() => handleToggleWatch(item)}
                    disabled={item.target_user_id === null || watchPending}
                    data-testid={`anomaly-watch-${item.id}`}
                  >
                    {item.target_user_id === null ? "☆" : "★"}
                  </button>
                </td>
                <td>
                  <button
                    type="button"
                    className={styles.dmButton}
                    aria-label={
                      item.target_user_id === null
                        ? "쪽지 — 대상 미식별로 발송 불가"
                        : `${item.target_user_email_masked ?? "사용자"}에게 쪽지 보내기`
                    }
                    title={
                      item.target_user_id === null
                        ? "대상 사용자 미식별 — 발송 불가"
                        : "쪽지 보내기"
                    }
                    onClick={() => handleOpenDM(item)}
                    disabled={item.target_user_id === null}
                    data-testid={`anomaly-dm-${item.id}`}
                  >
                    쪽지
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <AdminDMDialog
        open={dmTarget !== null}
        targetUserId={dmTarget?.userId ?? 0}
        targetEmail={dmTarget?.email ?? ""}
        onClose={() => setDmTarget(null)}
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
