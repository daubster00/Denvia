"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import {
  fetchNoticeDetail,
  fetchNoticeRecipients,
  type NoticeRecipientStatus,
  type NoticeTargetSegment,
} from "@/features/admin-cs-notices/api/notice";
import { sanitizeNoticeHtml } from "@/lib/sanitize";

import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ noticeId: string }>;
}

const SEGMENT_LABEL: Record<NoticeTargetSegment, string> = {
  all: "전체",
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

const USER_SEGMENT_LABEL: Record<string, string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

const PER_PAGE = 20;

function parseNoticeId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

function formatKoreanDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function AdminNoticeDetailPage({ params }: PageProps) {
  const { noticeId: noticeIdRaw } = use(params);
  const noticeId = parseNoticeId(noticeIdRaw);

  const [tab, setTab] = useState<NoticeRecipientStatus>("unread");
  const [readPage, setReadPage] = useState(1);
  const [unreadPage, setUnreadPage] = useState(1);

  const detailQuery = useQuery({
    queryKey: ["admin", "notice", noticeId, "detail"],
    queryFn: () => fetchNoticeDetail(noticeId as number),
    enabled: noticeId !== null,
  });

  const page = tab === "read" ? readPage : unreadPage;
  const setPage = tab === "read" ? setReadPage : setUnreadPage;

  const recipientsQuery = useQuery({
    queryKey: ["admin", "notice", noticeId, "recipients", tab, page],
    queryFn: () =>
      fetchNoticeRecipients(noticeId as number, tab, page, PER_PAGE),
    enabled: noticeId !== null,
    placeholderData: (prev) => prev,
  });

  if (noticeId === null) {
    return (
      <section className={styles.page}>
        <div className={styles.breadcrumb}>
          <Link href="/admin/content/notices" className={styles.backLink}>
            ← 쪽지 관리
          </Link>
        </div>
        <div className={styles.invalidBox} role="alert">
          잘못된 쪽지 ID입니다.
        </div>
      </section>
    );
  }

  const detail = detailQuery.data;
  const readCount = recipientsQuery.data?.read_count ?? 0;
  const unreadCount = recipientsQuery.data?.unread_count ?? 0;
  const totalCount = readCount + unreadCount;

  const items = recipientsQuery.data?.items ?? [];
  const total = recipientsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <section className={styles.page} aria-labelledby="admin-notice-detail-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/content/notices" className={styles.backLink}>
          ← 쪽지 관리
        </Link>
      </div>

      <section className={styles.summaryCard}>
        {detailQuery.isPending ? (
          <p className={styles.loading} role="status">불러오는 중…</p>
        ) : detailQuery.error || !detail ? (
          <p className={styles.errorBox} role="alert">
            쪽지 정보를 불러오지 못했습니다.
          </p>
        ) : (
          <>
            <h1 id="admin-notice-detail-title" className={styles.title}>
              {detail.title}
            </h1>
            <div className={styles.summaryMeta}>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>대상</span>
                {SEGMENT_LABEL[detail.target_segment]}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>발송 시각</span>
                {formatKoreanDate(detail.published_at)}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>전달 수</span>
                {detail.delivered_user_count.toLocaleString("ko-KR")}명
              </span>
            </div>
            <div
              className={styles.body}
              dangerouslySetInnerHTML={{
                __html: sanitizeNoticeHtml(detail.body_html),
              }}
            />
          </>
        )}
      </section>

      <section className={styles.statCards} aria-label="읽음/안 읽음 요약">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>총 발송</span>
          <span className={styles.statValue}>
            {totalCount.toLocaleString("ko-KR")}명
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>읽음</span>
          <span className={`${styles.statValue} ${styles.statValueRead}`}>
            {readCount.toLocaleString("ko-KR")}명
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>안 읽음</span>
          <span className={`${styles.statValue} ${styles.statValueUnread}`}>
            {unreadCount.toLocaleString("ko-KR")}명
          </span>
        </div>
      </section>

      <div className={styles.tabs} role="tablist" aria-label="수신자 그룹">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "unread"}
          className={`${styles.tab} ${tab === "unread" ? styles.tabActive : ""}`}
          onClick={() => setTab("unread")}
        >
          안 읽음
          <span className={styles.badge}>
            {unreadCount.toLocaleString("ko-KR")}
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "read"}
          className={`${styles.tab} ${tab === "read" ? styles.tabActive : ""}`}
          onClick={() => setTab("read")}
        >
          읽음
          <span className={styles.badge}>
            {readCount.toLocaleString("ko-KR")}
          </span>
        </button>
      </div>

      <section className={styles.tableWrap}>
        {recipientsQuery.isPending ? (
          <p className={styles.loading} role="status">불러오는 중…</p>
        ) : recipientsQuery.error ? (
          <p className={styles.errorBox} role="alert">
            수신자 목록을 불러오지 못했습니다.
          </p>
        ) : items.length === 0 ? (
          <p className={styles.empty}>
            {tab === "read"
              ? "아직 읽은 사용자가 없습니다."
              : "안 읽은 사용자가 없습니다."}
          </p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>이메일</th>
                <th>이름</th>
                <th>가입 유형</th>
                <th>발송 시각</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.user_id}>
                  <td>{row.email}</td>
                  <td>{row.name ?? "—"}</td>
                  <td>
                    {row.segment ? (
                      <span className={styles.segmentTag}>
                        {USER_SEGMENT_LABEL[row.segment] ?? row.segment}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{formatKoreanDate(row.delivered_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {total > 0 && (
        <nav className={styles.pagination} aria-label="페이지네이션">
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            이전
          </button>
          <span className={styles.pageInfo}>
            {page} / {totalPages} (총 {total.toLocaleString("ko-KR")}명)
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            다음
          </button>
        </nav>
      )}
    </section>
  );
}
