"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  NoticeApiError,
  deleteAdminDm,
  fetchAdminDmDetail,
} from "@/features/admin-cs-notices/api/notice";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import { sanitizeNoticeHtml } from "@/lib/sanitize";

import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ messageId: string }>;
}

function parseMessageId(raw: string): number | null {
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

export default function AdminDmDetailPage({ params }: PageProps) {
  const { messageId: rawId } = use(params);
  const messageId = parseMessageId(rawId);
  const router = useRouter();
  const queryClient = useQueryClient();

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["admin", "dm", messageId, "detail"],
    queryFn: () => fetchAdminDmDetail(messageId as number),
    enabled: messageId !== null,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteAdminDm(messageId as number),
    onSuccess: () => {
      setConfirmOpen(false);
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
      router.push("/admin/content/notices");
    },
    onError: (err: unknown) => {
      if (err instanceof NoticeApiError && err.code === "ADMIN_DM_NOT_FOUND") {
        setConfirmOpen(false);
        setDeleteError(null);
        queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });
        router.push("/admin/content/notices");
        return;
      }
      if (err instanceof NoticeApiError) setDeleteError(err.message);
      else setDeleteError("삭제에 실패했습니다.");
    },
  });

  if (messageId === null) {
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

  return (
    <section className={styles.page} aria-labelledby="admin-dm-detail-title">
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
            <span className={styles.kindBadge}>특정 사용자 쪽지</span>
            <div className={styles.summaryHead}>
              <h1 id="admin-dm-detail-title" className={styles.title}>
                {detail.title}
              </h1>
            </div>
            <div className={styles.summaryMeta}>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>발송 시각</span>
                {formatKoreanDate(detail.created_at)}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>작성 관리자</span>
                {detail.created_by_admin_id ?? "—"}
              </span>
              {detail.deleted_at && (
                <span className={styles.deletedStatus}>
                  사용자 휴지통 이동: {formatKoreanDate(detail.deleted_at)}
                </span>
              )}
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

      {detail && (
        <section className={styles.recipientCard} aria-label="받는 사용자">
          <div className={styles.recipientHead}>
            <h2 className={styles.recipientTitle}>받는 사용자</h2>
            <span
              className={`${styles.readStatus} ${
                detail.is_read ? styles.readStatusRead : styles.readStatusUnread
              }`}
            >
              {detail.is_read ? "읽음" : "안 읽음"}
            </span>
          </div>
          <div className={styles.recipientRow}>
            <span className={styles.recipientEmail}>
              {detail.target_user_email}
            </span>
            <span className={styles.recipientMeta}>
              {detail.target_user_name ? `${detail.target_user_name} · ` : ""}
              #{detail.target_user_id}
            </span>
            <Link
              href={`/admin/users/${detail.target_user_id}`}
              className={styles.backLink}
            >
              사용자 상세 →
            </Link>
          </div>
        </section>
      )}

      {detail && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.deleteBtn}
            onClick={() => {
              setDeleteError(null);
              setConfirmOpen(true);
            }}
            disabled={deleteMutation.isPending}
          >
            쪽지 회수(삭제)
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="쪽지를 삭제할까요?"
        description={
          detail
            ? `"${detail.title}" 쪽지를 삭제하면 받은 사용자(${detail.target_user_email})의 쪽지함에서도 즉시 회수됩니다. 복구할 수 없습니다.`
            : ""
        }
        confirmLabel="삭제"
        cancelLabel="취소"
        danger
        isSubmitting={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setConfirmOpen(false);
            setDeleteError(null);
          }
        }}
        onConfirm={() => deleteMutation.mutate()}
      />
    </section>
  );
}
