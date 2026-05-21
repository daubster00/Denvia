"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Option, Select } from "@wanteddev/wds";

import {
  BoardApiError,
  BoardCategory,
  BoardPostStatus,
  fetchBoardMeta,
  fetchBoardPosts,
} from "@/features/admin-board/api/board";

import styles from "./page.module.css";

const PER_PAGE = 20;

const STATUS_CLASS: Record<BoardPostStatus, string> = {
  review: styles.statusReview,
  in_progress: styles.statusInProgress,
  rejected: styles.statusRejected,
  on_hold: styles.statusOnHold,
};

function formatKoreanDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

function buildPageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const window: (number | "…")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) window.push("…");
  for (let i = start; i <= end; i++) window.push(i);
  if (end < total - 1) window.push("…");
  window.push(total);
  return window;
}

export default function AdminBoardListPage() {
  const router = useRouter();
  const [category, setCategory] = useState<BoardCategory | "">("");
  const [status, setStatus] = useState<BoardPostStatus | "">("");
  const [page, setPage] = useState(1);

  const metaQuery = useQuery({
    queryKey: ["admin-board", "meta"],
    queryFn: fetchBoardMeta,
    staleTime: 5 * 60_000,
  });

  const listQuery = useQuery({
    queryKey: ["admin-board", "posts", { category, status, page }],
    queryFn: () =>
      fetchBoardPosts({
        category: category || undefined,
        status: status || undefined,
        page,
        per_page: PER_PAGE,
      }),
  });

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PER_PAGE))
    : 1;

  const categoryLabel = (key: BoardCategory): string =>
    metaQuery.data?.categories.find((c) => c.key === key)?.label ?? key;
  const statusLabel = (key: BoardPostStatus): string =>
    metaQuery.data?.statuses.find((s) => s.key === key)?.label ?? key;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerText}>
          <h1 className={styles.title}>수정요청 게시판</h1>
          <p className={styles.caption}>
            프로젝트 수정 요청을 등록·추적하는 사내 게시판입니다. 상태 변경은 btmdesign 마스터 계정만 가능합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.primaryBtn}
          onClick={() => router.push("/admin/board/new")}
        >
          + 새 글 작성
        </button>
      </header>

      <div className={styles.filters}>
        <span className={styles.filterLabel}>카테고리</span>
        <div className={styles.filterSelectWrap}>
          <Select
            value={category}
            onChange={(v) => {
              setCategory(v as BoardCategory | "");
              setPage(1);
            }}
            placeholder="전체"
            width="180px"
          >
            <Option value="">전체</Option>
            {metaQuery.data?.categories.map((c) => (
              <Option key={c.key} value={c.key}>
                {c.label}
              </Option>
            ))}
          </Select>
        </div>
        <span className={styles.filterLabel}>상태</span>
        <div className={styles.filterSelectWrap}>
          <Select
            value={status}
            onChange={(v) => {
              setStatus(v as BoardPostStatus | "");
              setPage(1);
            }}
            placeholder="전체"
            width="180px"
          >
            <Option value="">전체</Option>
            {metaQuery.data?.statuses.map((s) => (
              <Option key={s.key} value={s.key}>
                {s.label}
              </Option>
            ))}
          </Select>
        </div>
      </div>

      {listQuery.isError ? (
        <div className={styles.errorBox}>
          {listQuery.error instanceof BoardApiError
            ? listQuery.error.message
            : "목록을 불러오지 못했습니다."}
        </div>
      ) : null}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th style={{ width: "5%" }}>#</th>
              <th style={{ width: "12%" }}>카테고리</th>
              <th style={{ width: "12%" }}>상태</th>
              <th>제목</th>
              <th style={{ width: "15%" }}>작성자</th>
              <th style={{ width: "16%" }}>작성일</th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <tr>
                <td colSpan={6} className={styles.empty}>
                  불러오는 중…
                </td>
              </tr>
            ) : listQuery.data && listQuery.data.items.length === 0 ? (
              <tr>
                <td colSpan={6} className={styles.empty}>
                  아직 등록된 글이 없습니다.
                </td>
              </tr>
            ) : (
              listQuery.data?.items.map((item) => (
                <tr
                  key={item.id}
                  onClick={() => router.push(`/admin/board/${item.id}`)}
                >
                  <td>{item.id}</td>
                  <td>
                    <span className={styles.categoryChip}>
                      {categoryLabel(item.category)}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`${styles.statusBadge} ${STATUS_CLASS[item.status]}`}
                    >
                      {statusLabel(item.status)}
                    </span>
                  </td>
                  <td>
                    <Link
                      href={`/admin/board/${item.id}`}
                      className={styles.titleCell}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {item.title}
                    </Link>
                    {item.comment_count > 0 && (
                      <span className={styles.commentBadge}>
                        {item.comment_count}
                      </span>
                    )}
                  </td>
                  <td>{item.author_display}</td>
                  <td>{formatKoreanDate(item.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {listQuery.data && listQuery.data.total > 0 && (
        <nav className={styles.pager} aria-label="페이지네이션">
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page <= 1}
            onClick={() => setPage(1)}
            aria-label="첫 페이지"
          >
            «
          </button>
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            aria-label="이전 페이지"
          >
            ‹
          </button>
          {buildPageWindow(page, totalPages).map((p, idx) =>
            p === "…" ? (
              <span key={`gap-${idx}`} className={styles.pagerGap}>
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                className={`${styles.pagerBtn} ${p === page ? styles.pagerBtnActive : ""}`}
                onClick={() => setPage(p)}
                aria-current={p === page ? "page" : undefined}
              >
                {p}
              </button>
            ),
          )}
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            aria-label="다음 페이지"
          >
            ›
          </button>
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page >= totalPages}
            onClick={() => setPage(totalPages)}
            aria-label="마지막 페이지"
          >
            »
          </button>
          <span className={styles.pagerInfo}>
            총 {listQuery.data.total.toLocaleString("ko-KR")}개
          </span>
        </nav>
      )}
    </div>
  );
}
