"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  PopupListItem,
  deletePopup,
  fetchPopups,
  togglePopupActive,
} from "@/features/admin-content/api/popup";
import { PopupListTable } from "@/features/admin-content/components/PopupListTable";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import styles from "./page.module.css";

export default function AdminPopupsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [deletingItem, setDeletingItem] = useState<PopupListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const popupsQuery = useQuery({
    queryKey: ["admin", "popups", page],
    queryFn: () => fetchPopups(page, 20),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      togglePopupActive(id, isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "popups"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePopup(id),
    onSuccess: () => {
      setDeletingItem(null);
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "popups"] });
    },
    onError: (err: unknown) => {
      // 다른 관리자가 먼저 삭제한 경우(404) 다이얼로그를 닫고 목록을 갱신.
      if (err instanceof ApiError && err.code === "POPUP_NOT_FOUND") {
        setDeletingItem(null);
        setDeleteError(null);
        queryClient.invalidateQueries({ queryKey: ["admin", "popups"] });
        return;
      }
      if (err instanceof ApiError) {
        setDeleteError(err.message);
      } else {
        setDeleteError("삭제에 실패했습니다.");
      }
    },
  });

  const totalPages = popupsQuery.data
    ? Math.max(1, Math.ceil(popupsQuery.data.total / popupsQuery.data.per_page))
    : 1;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.heading}>팝업 관리</h1>
          <p className={styles.subheading}>
            서비스 메인에 노출되는 팝업을 생성·편집·활성/비활성·삭제합니다.
          </p>
        </div>
        <Link href="/admin/content/popups/new" className={styles.newBtn}>
          + 새 팝업 작성
        </Link>
      </header>

      <section className={styles.tableWrap}>
        {popupsQuery.isPending ? (
          <p className={styles.loading} role="status">
            불러오는 중…
          </p>
        ) : popupsQuery.error ? (
          <p className={styles.error} role="alert">
            팝업 목록을 불러오지 못했습니다.
          </p>
        ) : (
          <PopupListTable
            items={popupsQuery.data?.items ?? []}
            togglingId={
              toggleMutation.isPending
                ? (toggleMutation.variables?.id ?? null)
                : null
            }
            onEdit={(id) => router.push(`/admin/content/popups/${id}`)}
            onToggle={(id, isActive) =>
              toggleMutation.mutate({ id, isActive })
            }
            onDelete={(item) => {
              setDeleteError(null);
              setDeletingItem(item);
            }}
          />
        )}
      </section>

      {popupsQuery.data && popupsQuery.data.total > 0 ? (
        <nav className={styles.pagination} aria-label="페이지네이션">
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            이전
          </button>
          <span className={styles.pageInfo}>
            {page} / {totalPages} (총 {popupsQuery.data.total}개)
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            다음
          </button>
        </nav>
      ) : null}

      <ConfirmDialog
        open={Boolean(deletingItem)}
        title="팝업을 삭제할까요?"
        description={
          deletingItem
            ? `"${deletingItem.title}" 팝업을 삭제하면 사용자에게 더 이상 노출되지 않습니다. 삭제된 데이터는 즉시 복구할 수 없습니다.`
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
