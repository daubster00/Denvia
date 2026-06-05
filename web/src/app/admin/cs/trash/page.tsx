"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchTrashList } from "@/features/admin-cs-trash/api/trash";
import type {
  InboxMessageType,
  TrashListItem,
} from "@/features/admin-cs-trash/api/trash";

import styles from "./page.module.css";

const PER_PAGE = 20;

const TYPE_LABEL: Record<InboxMessageType, string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
  admin_dm: "관리자 쪽지",
};

function formatKoreanDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatKoreanDateOnly(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("ko-KR", { dateStyle: "medium" });
}

function daysUntilPurge(iso: string): number {
  const target = new Date(iso).getTime();
  const now = Date.now();
  return Math.max(0, Math.ceil((target - now) / (1000 * 60 * 60 * 24)));
}

export default function CsTrashPage() {
  const [page, setPage] = useState(1);

  const listQuery = useQuery({
    queryKey: ["admin", "cs", "trash", page],
    queryFn: () => fetchTrashList(page, PER_PAGE),
  });

  const total = listQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <section className={styles.page} aria-labelledby="cs-trash-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="cs-trash-title" className={styles.title}>
            CS · 휴지통
          </h1>
          <p className={styles.caption}>
            사용자가 본인 쪽지함에서 삭제한 쪽지입니다. 30일 동안 보관되며,
            기간이 지나면 자동으로 영구 삭제됩니다. 항목을 클릭하면 본문을
            확인하고 복구 또는 즉시 영구 삭제할 수 있습니다.
          </p>
        </div>
        <div className={styles.counterChip} aria-live="polite">
          전체 {total.toLocaleString("ko-KR")}건
        </div>
      </header>

      {listQuery.isPending ? (
        <p className={styles.loading} role="status">
          불러오는 중…
        </p>
      ) : listQuery.error ? (
        <p className={styles.errorBox} role="alert">
          휴지통 목록을 불러오지 못했습니다.
        </p>
      ) : (listQuery.data?.items.length ?? 0) === 0 ? (
        <div className={styles.emptyBox}>
          <p className={styles.emptyTitle}>휴지통이 비어 있습니다.</p>
          <p className={styles.emptyHint}>
            사용자가 쪽지함에서 쪽지를 삭제하면 이곳에 30일 동안 보관됩니다.
          </p>
        </div>
      ) : (
        <>
          <ul className={styles.list}>
            {listQuery.data!.items.map((item) => (
              <TrashRow key={item.message_id} item={item} />
            ))}
          </ul>

          {totalPages > 1 && (
            <nav className={styles.pager} aria-label="페이지">
              <button
                type="button"
                className={styles.pagerBtn}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
              >
                이전
              </button>
              <span className={styles.pagerStatus}>
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className={styles.pagerBtn}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                다음
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

function TrashRow({ item }: { item: TrashListItem }) {
  const days = daysUntilPurge(item.permanent_purge_at);
  const purgeSoon = days <= 3;

  return (
    <li className={styles.row}>
      <Link
        href={`/admin/cs/trash/${item.message_id}`}
        className={styles.rowLink}
      >
        <div className={styles.rowMain}>
          <div className={styles.rowHead}>
            <span className={styles.typeBadge}>{TYPE_LABEL[item.type]}</span>
            <h2 className={styles.rowTitle}>{item.title}</h2>
          </div>
          <p className={styles.rowMeta}>
            <span className={styles.metaLabel}>받은 사용자</span>
            <span className={styles.metaValue}>{item.user_email}</span>
            {item.user_name && (
              <span className={styles.metaSub}>({item.user_name})</span>
            )}
          </p>
        </div>

        <div className={styles.rowSide}>
          <div className={styles.dateBlock}>
            <span className={styles.dateLabel}>휴지통 이동</span>
            <span className={styles.dateValue}>
              {formatKoreanDate(item.deleted_at)}
            </span>
          </div>
          <div
            className={
              purgeSoon ? styles.purgeBlockSoon : styles.purgeBlock
            }
          >
            <span className={styles.purgeLabel}>
              자동 영구 삭제 예정일
            </span>
            <span className={styles.purgeValue}>
              {formatKoreanDateOnly(item.permanent_purge_at)}
            </span>
            <span className={styles.purgeRemain}>D-{days}</span>
          </div>
        </div>
      </Link>
    </li>
  );
}
