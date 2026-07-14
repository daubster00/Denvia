"use client";

import Link from "next/link";
import { IconDownload } from "@wanteddev/wds-icon";
import type { FeedbackItem } from "../api/analytics";
import styles from "./FeedbackDetailTable.module.css";

type Unit = "day" | "week" | "month";

interface FeedbackDetailTableProps {
  items: FeedbackItem[];
  /** 일/주/월 토글 단위 — 하단 목록을 같은 단위로 묶어 표시한다(#103). */
  unit: Unit;
  total: number;
  page: number;
  perPage: number;
  onPageChange: (page: number) => void;
  onRowClick: (item: FeedbackItem) => void;
  onExport: () => void;
  onToggleReviewed: (item: FeedbackItem) => void;
  pendingReviewIds?: Set<number>;
  onDelete: (item: FeedbackItem) => void;
  pendingDeleteIds?: Set<number>;
  isExporting?: boolean;
  exportError?: string | null;
}

const COL_SPAN = 8;

export function FeedbackDetailTable({
  items,
  unit,
  total,
  page,
  perPage,
  onPageChange,
  onRowClick,
  onExport,
  onToggleReviewed,
  pendingReviewIds,
  onDelete,
  pendingDeleteIds,
  isExporting = false,
  exportError = null,
}: FeedbackDetailTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const groups = groupByUnit(items, unit);

  return (
    <div className={styles.wrapper}>
      <div className={styles.tableActions}>
        <p className={styles.totalCount}>전체 {total.toLocaleString()}건</p>
        <button
          type="button"
          className={styles.exportBtn}
          onClick={onExport}
          aria-label="현재 필터 기준으로 엑셀 내보내기"
          disabled={isExporting}
        >
          <IconDownload aria-hidden="true" />
          <span>{isExporting ? "내보내는 중" : "엑셀 내보내기"}</span>
        </button>
      </div>
      {exportError && (
        <p className={styles.exportError} role="alert">
          {exportError}
        </p>
      )}

      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <colgroup>
            <col className={styles.colQuestion} />
            <col className={styles.colAnswer} />
            <col className={styles.colRating} />
            <col className={styles.colSegment} />
            <col className={styles.colDate} />
            <col className={styles.colReviewStatus} />
            <col className={styles.colReviewAction} />
            <col className={styles.colDeleteAction} />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={styles.thQuestion}>질문</th>
              <th scope="col" className={styles.thAnswer}>답변</th>
              <th scope="col" className={styles.thRating}>피드백</th>
              <th scope="col" className={styles.thSegment}>계정</th>
              <th scope="col" className={styles.thDate}>제출일시</th>
              <th scope="col" className={styles.thReviewStatus}>검토 상태</th>
              <th scope="col" className={styles.thReviewAction}>검토 작업</th>
              <th scope="col" className={styles.thDeleteAction}>삭제</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={COL_SPAN} className={styles.emptyRow} role="status">
                  이 기간에 피드백이 없습니다.
                </td>
              </tr>
            )}
            {groups.map((group) => (
              <GroupRows
                key={group.key}
                label={group.label}
                count={group.items.length}
                items={group.items}
                onRowClick={onRowClick}
                onToggleReviewed={onToggleReviewed}
                pendingReviewIds={pendingReviewIds}
                onDelete={onDelete}
                pendingDeleteIds={pendingDeleteIds}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <button
          type="button"
          className={styles.pageBtn}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="이전 페이지"
        >
          이전
        </button>
        <span className={styles.pageInfo}>
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className={styles.pageBtn}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="다음 페이지"
        >
          다음
        </button>
      </div>
    </div>
  );
}

interface GroupRowsProps {
  label: string;
  count: number;
  items: FeedbackItem[];
  onRowClick: (item: FeedbackItem) => void;
  onToggleReviewed: (item: FeedbackItem) => void;
  pendingReviewIds?: Set<number>;
  onDelete: (item: FeedbackItem) => void;
  pendingDeleteIds?: Set<number>;
}

function GroupRows({
  label,
  count,
  items,
  onRowClick,
  onToggleReviewed,
  pendingReviewIds,
  onDelete,
  pendingDeleteIds,
}: GroupRowsProps) {
  return (
    <>
      <tr className={styles.groupHeaderRow}>
        <th
          scope="colgroup"
          colSpan={COL_SPAN}
          className={styles.groupHeaderCell}
        >
          <span className={styles.groupHeaderLabel}>{label}</span>
          <span className={styles.groupHeaderCount}>{count}건</span>
        </th>
      </tr>
      {items.map((item) => {
        const reviewed = item.reviewed_at != null;
        const pending = pendingReviewIds?.has(item.qa_log_id) ?? false;
        const deleting = pendingDeleteIds?.has(item.qa_log_id) ?? false;
        return (
          <tr
            key={item.qa_log_id}
            className={styles.row}
            onClick={() => onRowClick(item)}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") onRowClick(item);
            }}
            aria-label="피드백 상세 보기"
          >
            <td className={styles.td}>
              <span className={styles.tdClamp}>{item.question_text}</span>
            </td>
            <td className={styles.td}>
              <span className={styles.tdClamp}>{item.answer_text ?? "—"}</span>
            </td>
            <td className={styles.td}>
              <span
                className={
                  item.rating === "good" ? styles.badgeGood : styles.badgeBad
                }
              >
                {item.rating === "good" ? "👍 GOOD" : "👎 BAD"}
              </span>
            </td>
            <td className={styles.td}>
              {item.user_id !== null && item.email ? (
                <Link
                  href={`/admin/users/${item.user_id}`}
                  className={styles.accountLink}
                  onClick={(e) => e.stopPropagation()}
                  title={`${item.email} 고객 관리 페이지로 이동`}
                >
                  {item.email}
                </Link>
              ) : (
                <span className={styles.accountAnon}>탈퇴회원</span>
              )}
            </td>
            <td className={styles.td}>{formatKst(item.created_at)}</td>
            <td className={styles.td}>
              <span
                className={
                  reviewed ? styles.statusReviewed : styles.statusPending
                }
              >
                {reviewed ? "✓ 검토완료" : "미검토"}
              </span>
            </td>
            <td className={styles.td}>
              <button
                type="button"
                className={reviewed ? styles.reviewBtnUndo : styles.reviewBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleReviewed(item);
                }}
                disabled={pending}
                aria-pressed={reviewed}
                title={
                  reviewed
                    ? "검토완료 해제 (미검토로 되돌리기)"
                    : "이 피드백을 검토완료로 표시"
                }
              >
                {pending ? "처리 중…" : reviewed ? "되돌리기" : "검토완료"}
              </button>
            </td>
            <td className={styles.td}>
              <button
                type="button"
                className={styles.deleteBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(item);
                }}
                disabled={deleting}
                title="이 피드백을 삭제"
                aria-label="이 피드백을 삭제"
              >
                {deleting ? "삭제 중…" : "삭제"}
              </button>
            </td>
          </tr>
        );
      })}
    </>
  );
}

interface FeedbackGroup {
  key: string;
  label: string;
  items: FeedbackItem[];
}

/**
 * 목록을 일/주/월 단위로 묶는다(#103). 서버가 created_at 내림차순으로
 * 정렬해 보내므로 순서를 유지하며 같은 버킷끼리 그룹핑한다.
 */
function groupByUnit(items: FeedbackItem[], unit: Unit): FeedbackGroup[] {
  const groups: FeedbackGroup[] = [];
  const indexByKey = new Map<string, number>();
  for (const item of items) {
    const { key, label } = bucketOf(item.created_at, unit);
    let idx = indexByKey.get(key);
    if (idx === undefined) {
      idx = groups.length;
      indexByKey.set(key, idx);
      groups.push({ key, label, items: [] });
    }
    groups[idx].items.push(item);
  }
  return groups;
}

/** created_at(ISO) → 단위별 버킷 key/label (KST 기준). */
function bucketOf(iso: string, unit: Unit): { key: string; label: string } {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { key: iso, label: iso };
  // KST 기준 연/월/일 추출.
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d); // YYYY-MM-DD
  const [y, m, day] = parts.split("-");

  if (unit === "month") {
    return { key: `${y}-${m}`, label: `${y}년 ${Number(m)}월` };
  }
  if (unit === "week") {
    // KST 기준 그 주의 일요일을 버킷 시작으로 삼는다.
    const kstNoon = new Date(`${y}-${m}-${day}T12:00:00+09:00`);
    const dow = kstNoon.getUTCDay(); // 0=일 ~ 6=토 (UTC 기준이나 정오라 KST 요일과 동일)
    const sunday = new Date(kstNoon);
    sunday.setUTCDate(kstNoon.getUTCDate() - dow);
    const sp = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(sunday);
    const [sy, sm, sd] = sp.split("-");
    return {
      key: `W-${sy}-${sm}-${sd}`,
      label: `${Number(sm)}/${Number(sd)} 주 (일요일 시작)`,
    };
  }
  // day
  return { key: `${y}-${m}-${day}`, label: `${y}년 ${Number(m)}월 ${Number(day)}일` };
}

function formatKst(iso: string): string {
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return iso;
  }
}
