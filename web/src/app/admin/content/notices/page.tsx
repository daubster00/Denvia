"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  NoticeCreateDialog,
  type NoticeCreateSubmitPayload,
} from "@/features/admin-cs-notices/components/NoticeCreateDialog";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  NoticeApiError,
  createNotice,
  deleteAdminDm,
  deleteNotice,
  fetchInboxPreviewConfig,
  fetchNotices,
  updateInboxPreviewConfig,
  type NoticeListItem,
  type NoticeTargetFilter,
  type NoticeTargetSegment,
} from "@/features/admin-cs-notices/api/notice";
import { sendAdminDM } from "@/features/admin-users/api/users";

import styles from "./page.module.css";

const SEGMENT_LABEL: Record<NoticeTargetSegment, string> = {
  all: "전체",
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

const FILTER_CHOICES: Array<{ value: NoticeTargetFilter; label: string }> = [
  { value: "all", label: "전체" },
  { value: "broadcast", label: "공지만" },
  { value: "dm", label: "개별 쪽지만" },
];

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

function renderTargetCell(item: NoticeListItem) {
  if (item.item_type === "admin_dm") {
    return (
      <>
        <span className={`${styles.targetBadge} ${styles.targetBadgeDM}`}>
          특정 사용자
        </span>
        {item.target_user_email && (
          <span className={styles.targetEmail}>{item.target_user_email}</span>
        )}
      </>
    );
  }
  const seg = item.target_segment;
  return (
    <span className={styles.targetBadge}>
      {seg ? SEGMENT_LABEL[seg] : "—"}
    </span>
  );
}

export default function AdminCsNoticesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [targetFilter, setTargetFilter] = useState<NoticeTargetFilter>("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deletingItem, setDeletingItem] = useState<NoticeListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const noticesQuery = useQuery({
    queryKey: ["admin", "notices", page, targetFilter],
    queryFn: () => fetchNotices(page, PER_PAGE, targetFilter),
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
    mutationFn: async (payload: NoticeCreateSubmitPayload) => {
      if (payload.target_type === "user") {
        if (!payload.target_user_id) {
          throw new Error("target_user_id missing");
        }
        await sendAdminDM(payload.target_user_id, {
          title: payload.title,
          body_html: payload.body_html,
        });
        return;
      }
      await createNotice({
        title: payload.title,
        body_html: payload.body_html,
        target_segment: payload.target_segment ?? "all",
      });
    },
    onSuccess: () => {
      setCreateOpen(false);
      setCreateError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
    },
    onError: (err: unknown) => {
      if (err instanceof NoticeApiError) setCreateError(err.message);
      else if (err instanceof Error && err.message) setCreateError(err.message);
      else setCreateError("발송에 실패했습니다.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (item: NoticeListItem) =>
      item.item_type === "admin_dm"
        ? deleteAdminDm(item.id)
        : deleteNotice(item.id),
    onSuccess: () => {
      setDeletingItem(null);
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
    },
    onError: (err: unknown) => {
      if (
        err instanceof NoticeApiError &&
        (err.code === "NOTICE_NOT_FOUND" || err.code === "ADMIN_DM_NOT_FOUND")
      ) {
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
            전체/세그먼트 공지와 특정 사용자에게 보낸 개별 쪽지를 한곳에서 관리합니다. 작성과 동시에 발송되며, 삭제하면 사용자 쪽지함에서도 회수됩니다.
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

      <div className={styles.filterBar} role="tablist" aria-label="대상 필터">
        <span className={styles.filterLabel}>유형</span>
        {FILTER_CHOICES.map((choice) => (
          <button
            key={choice.value}
            type="button"
            role="tab"
            aria-selected={targetFilter === choice.value}
            className={`${styles.filterChip} ${
              targetFilter === choice.value ? styles.filterChipActive : ""
            }`}
            onClick={() => {
              setTargetFilter(choice.value);
              setPage(1);
            }}
          >
            {choice.label}
          </button>
        ))}
      </div>

      <section className={styles.tableWrap}>
        {noticesQuery.isPending ? (
          <p className={styles.loading} role="status">불러오는 중…</p>
        ) : noticesQuery.error ? (
          <p className={styles.errorBox} role="alert">
            쪽지 목록을 불러오지 못했습니다.
          </p>
        ) : (noticesQuery.data?.items.length ?? 0) === 0 ? (
          <p className={styles.empty}>
            {targetFilter === "dm"
              ? "발송한 개별 쪽지가 없습니다."
              : targetFilter === "broadcast"
              ? "발송한 공지가 없습니다."
              : "아직 발송한 쪽지가 없습니다. 우측 상단 “새 쪽지 작성”으로 첫 쪽지를 보내보세요."}
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
              {noticesQuery.data!.items.map((item) => {
                const detailHref =
                  item.item_type === "admin_dm"
                    ? `/admin/content/notices/dm/${item.id}`
                    : `/admin/content/notices/${item.id}`;
                const goToDetail = () => router.push(detailHref);
                const rowKey = `${item.item_type}-${item.id}`;
                return (
                  <tr
                    key={rowKey}
                    role="button"
                    tabIndex={0}
                    aria-label={`${item.title} 상세 보기`}
                    className={styles.clickableRow}
                    onClick={goToDetail}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        goToDetail();
                      }
                    }}
                  >
                    <td className={styles.cellTitle}>{item.title}</td>
                    <td>{renderTargetCell(item)}</td>
                    <td>{formatKoreanDate(item.published_at)}</td>
                    <td className={styles.cellNumeric}>
                      {item.delivered_user_count.toLocaleString("ko-KR")}
                    </td>
                    <td className={styles.cellAction}>
                      <button
                        type="button"
                        className={styles.deleteBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteError(null);
                          setDeletingItem(item);
                        }}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                );
              })}
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
          onSubmit={(payload) => createMutation.mutate(payload)}
        />
      )}

      <ConfirmDialog
        open={Boolean(deletingItem)}
        title="쪽지를 삭제할까요?"
        description={
          deletingItem
            ? deletingItem.item_type === "admin_dm"
              ? `"${deletingItem.title}" 쪽지를 삭제하면 받은 사용자(${
                  deletingItem.target_user_email ?? ""
                })의 쪽지함에서도 즉시 회수됩니다. 복구할 수 없습니다.`
              : `"${deletingItem.title}" 쪽지를 삭제하면 이미 발송된 ${deletingItem.delivered_user_count.toLocaleString(
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
          if (deletingItem) deleteMutation.mutate(deletingItem);
        }}
      />
    </main>
  );
}
