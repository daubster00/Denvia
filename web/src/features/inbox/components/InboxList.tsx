"use client";

/** InboxList — 쪽지함 페이지네이션 + 상태별 UI. Story 4.5. */

import { useState } from "react";

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { IconInbox } from "@wanteddev/wds-icon";

import { deleteInboxMessage } from "../api";
import { useInbox } from "../hooks/useInbox";
import { useMarkRead } from "../hooks/useMarkRead";
import type { InboxFilter, InboxItem } from "../types";
import { NoticeCard } from "./NoticeCard";
import { NoticeDetailDialog } from "./NoticeDetailDialog";
import styles from "./InboxList.module.css";

interface InboxListProps {
  filter: InboxFilter;
}

const PER_PAGE_OPTIONS = [10, 20, 50] as const;

export function InboxList({ filter }: InboxListProps) {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState<number>(20);
  const [activeItem, setActiveItem] = useState<InboxItem | null>(null);

  const { data, isLoading, isError, refetch } = useInbox(page, perPage, filter);
  const markRead = useMarkRead();
  const qc = useQueryClient();
  const deleteMutation = useMutation<void, Error, number>({
    mutationFn: (messageId) => deleteInboxMessage(messageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me", "inbox"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "unread-count"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "preview"] });
    },
  });

  function handleCardClick(item: InboxItem) {
    if (!item.is_read) {
      markRead.mutate(item.message_id);
    }
    // 문의 답변 쪽지는 본문 팝업 대신 원본 문의 상세로 이동.
    if (item.inquiry_id != null) {
      router.push(`/my/inquiries/${item.inquiry_id}`);
      return;
    }
    setActiveItem(item);
  }

  if (isLoading) {
    return <div className={styles.state}>쪽지를 불러오는 중…</div>;
  }

  if (isError || !data) {
    return (
      <div className={styles.state} role="alert">
        쪽지를 불러오지 못했습니다
        <button type="button" onClick={() => refetch()} className={styles.retryBtn}>
          새로고침
        </button>
      </div>
    );
  }

  if (data.total === 0) {
    return (
      <div className={styles.state}>
        <IconInbox className={styles.emptyIcon} aria-hidden="true" />
        아직 받은 쪽지가 없어요.
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.per_page));

  return (
    <div className={styles.wrapper}>
      <ul className={styles.list}>
        {data.items.map((item) => (
          <li key={item.message_id}>
            <NoticeCard
              item={item}
              onClick={() => handleCardClick(item)}
              onDelete={(id) => deleteMutation.mutate(id)}
            />
          </li>
        ))}
      </ul>

      <div className={styles.pagination}>
        <label className={styles.perPageLabel}>
          페이지당
          <select
            value={perPage}
            onChange={(e) => {
              setPerPage(Number(e.target.value));
              setPage(1);
            }}
            className={styles.perPageSelect}
            aria-label="페이지당 쪽지 수"
          >
            {PER_PAGE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <div className={styles.pagerControls}>
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className={styles.pagerBtn}
          >
            이전
          </button>
          <span className={styles.pagerLabel}>
            {data.page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className={styles.pagerBtn}
          >
            다음
          </button>
        </div>
      </div>

      {activeItem && (
        <NoticeDetailDialog
          item={activeItem}
          onClose={() => setActiveItem(null)}
        />
      )}
    </div>
  );
}
