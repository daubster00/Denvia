"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { NoticeCreateDialog } from "@/features/admin-cs-notices/components/NoticeCreateDialog";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  NoticeApiError,
  createNotice,
  deleteNotice,
  fetchInboxPreviewConfig,
  fetchNotices,
  updateInboxPreviewConfig,
  type NoticeFormInput,
  type NoticeListItem,
  type NoticeTargetSegment,
} from "@/features/admin-cs-notices/api/notice";

import styles from "./page.module.css";

const SEGMENT_LABEL: Record<NoticeTargetSegment, string> = {
  all: "전체",
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

const PER_PAGE = 20;

function formatKoreanDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function AdminCsNoticesPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deletingItem, setDeletingItem] = useState<NoticeListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const noticesQuery = useQuery({
    queryKey: ["admin", "notices", page],
    queryFn: () => fetchNotices(page, PER_PAGE),
  });

  const previewConfigQuery = useQuery({
    queryKey: ["admin", "inbox-preview-config"],
    queryFn: fetchInboxPreviewConfig,
  });

  const previewConfigMutation = useMutation({
    mutationFn: (maxCount: number) => updateInboxPreviewConfig(maxCount),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["admin", "inbox-preview-config"],
      });
    },
  });

  const createMutation = useMutation({
    mutationFn: (input: NoticeFormInput) => createNotice(input),
    onSuccess: () => {
      setCreateOpen(false);
      setCreateError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
    },
    onError: (err: unknown) => {
      if (err instanceof NoticeApiError) setCreateError(err.message);
      else setCreateError("발송에 실패했습니다.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteNotice(id),
    onSuccess: () => {
      setDeletingItem(null);
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
    },
    onError: (err: unknown) => {
      if (err instanceof NoticeApiError && err.code === "NOTICE_NOT_FOUND") {
        setDeletingItem(null);
        setDeleteError(null);
        queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
        return;
      }
      if (err instanceof NoticeApiError) setDeleteError(err.message);
      else setDeleteError("삭제에 실패했습니다.");
    },
  });

  const total = noticesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.heading}>쪽지 관리</h1>
          <p className={styles.subheading}>
            로그인한 사용자의 쪽지함으로 보낼 알림글을 작성·삭제합니다. 작성과 동시에 발송되며, 삭제하면 사용자 쪽지함에서도 회수됩니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.newBtn}
          onClick={() => {
            setCreateError(null);
            setCreateOpen(true);
          }}
        >
          + 새 쪽지 작성
        </button>
      </header>

      <section className={styles.previewConfigCard} aria-labelledby="preview-config-heading">
        <div className={styles.previewConfigHead}>
          <h2 id="preview-config-heading" className={styles.previewConfigTitle}>
            동시 노출 최대 개수
          </h2>
          <p className={styles.previewConfigCaption}>
            로그인 직후 쪽지함 아이콘 아래로 자동 펼쳐지는 미리보기에 동시에 보일 카드 수입니다. (1~5)
          </p>
        </div>
        <div className={styles.previewConfigControl}>
          {previewConfigQuery.isPending ? (
            <span className={styles.muted}>불러오는 중…</span>
          ) : previewConfigQuery.error ? (
            <span className={styles.error}>설정을 불러오지 못했습니다.</span>
          ) : (
            <>
              <select
                className={styles.previewConfigSelect}
                value={previewConfigQuery.data?.max_count ?? 1}
                disabled={previewConfigMutation.isPending}
                onChange={(e) =>
                  previewConfigMutation.mutate(Number(e.target.value))
                }
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}개
                  </option>
                ))}
              </select>
              {previewConfigMutation.isPending && (
                <span className={styles.muted}>저장 중…</span>
              )}
              {previewConfigMutation.isError && (
                <span className={styles.error}>저장에 실패했습니다.</span>
              )}
            </>
          )}
        </div>
      </section>

      <section className={styles.tableWrap}>
        {noticesQuery.isPending ? (
          <p className={styles.loading} role="status">불러오는 중…</p>
        ) : noticesQuery.error ? (
          <p className={styles.errorBox} role="alert">
            쪽지 목록을 불러오지 못했습니다.
          </p>
        ) : (noticesQuery.data?.items.length ?? 0) === 0 ? (
          <p className={styles.empty}>
            아직 발송한 쪽지가 없습니다. 우측 상단 “새 쪽지 작성”으로 첫 쪽지를 보내보세요.
          </p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>제목</th>
                <th>대상</th>
                <th>발송 시각</th>
                <th>전달 수</th>
                <th aria-label="액션" />
              </tr>
            </thead>
            <tbody>
              {noticesQuery.data!.items.map((item) => (
                <tr key={item.id}>
                  <td className={styles.cellTitle}>{item.title}</td>
                  <td>{SEGMENT_LABEL[item.target_segment]}</td>
                  <td>{formatKoreanDate(item.published_at)}</td>
                  <td className={styles.cellNumeric}>
                    {item.delivered_user_count.toLocaleString("ko-KR")}
                  </td>
                  <td className={styles.cellAction}>
                    <button
                      type="button"
                      className={styles.deleteBtn}
                      onClick={() => {
                        setDeleteError(null);
                        setDeletingItem(item);
                      }}
                    >
                      삭제
                    </button>
                  </td>
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
            {page} / {totalPages} (총 {total.toLocaleString("ko-KR")}개)
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

      {createOpen && (
        <NoticeCreateDialog
          isSubmitting={createMutation.isPending}
          errorMessage={createError}
          onClose={() => {
            if (!createMutation.isPending) {
              setCreateOpen(false);
              setCreateError(null);
            }
          }}
          onSubmit={(input) => createMutation.mutate(input)}
        />
      )}

      <ConfirmDialog
        open={Boolean(deletingItem)}
        title="쪽지를 삭제할까요?"
        description={
          deletingItem
            ? `"${deletingItem.title}" 쪽지를 삭제하면 이미 발송된 ${deletingItem.delivered_user_count.toLocaleString(
                "ko-KR",
              )}명의 쪽지함에서도 즉시 회수됩니다. 복구할 수 없습니다.`
            : ""
        }
        confirmLabel="삭제"
        cancelLabel="취소"
        danger
        isSubmitting={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setDeletingItem(null);
            setDeleteError(null);
          }
        }}
        onConfirm={() => {
          if (deletingItem) deleteMutation.mutate(deletingItem.id);
        }}
      />
    </main>
  );
}
