"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  TrashApiError,
  fetchTrashDetail,
  hardDeleteTrashMessage,
  restoreTrashMessage,
} from "@/features/admin-cs-trash/api/trash";
import type { InboxMessageType } from "@/features/admin-cs-trash/api/trash";

import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ messageId: string }>;
}

const TYPE_LABEL: Record<InboxMessageType, string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
  admin_dm: "관리자 쪽지",
};

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

export default function CsTrashDetailPage({ params }: PageProps) {
  const { messageId: rawId } = use(params);
  const messageId = parseMessageId(rawId);
  const router = useRouter();
  const queryClient = useQueryClient();

  const [restoreOpen, setRestoreOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["admin", "cs", "trash", messageId, "detail"],
    queryFn: () => fetchTrashDetail(messageId as number),
    enabled: messageId !== null,
  });

  const restoreMutation = useMutation({
    mutationFn: () => restoreTrashMessage(messageId as number),
    onSuccess: () => {
      setRestoreOpen(false);
      setRestoreError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "cs", "trash"] });
      router.push("/admin/cs/trash");
    },
    onError: (err: unknown) => {
      if (err instanceof TrashApiError) setRestoreError(err.message);
      else setRestoreError("복구에 실패했습니다.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => hardDeleteTrashMessage(messageId as number),
    onSuccess: () => {
      setDeleteOpen(false);
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "cs", "trash"] });
      router.push("/admin/cs/trash");
    },
    onError: (err: unknown) => {
      if (err instanceof TrashApiError && err.code === "TRASH_NOT_FOUND") {
        setDeleteOpen(false);
        setDeleteError(null);
        queryClient.invalidateQueries({ queryKey: ["admin", "cs", "trash"] });
        router.push("/admin/cs/trash");
        return;
      }
      if (err instanceof TrashApiError) setDeleteError(err.message);
      else setDeleteError("영구 삭제에 실패했습니다.");
    },
  });

  if (messageId === null) {
    return (
      <section className={styles.page}>
        <div className={styles.breadcrumb}>
          <Link href="/admin/cs/trash" className={styles.backLink}>
            ← 휴지통 목록
          </Link>
        </div>
        <div className={styles.invalidBox} role="alert">
          잘못된 쪽지 ID입니다.
        </div>
      </section>
    );
  }

  const detail = detailQuery.data;
  const busy = restoreMutation.isPending || deleteMutation.isPending;

  return (
    <section className={styles.page} aria-labelledby="cs-trash-detail-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/cs/trash" className={styles.backLink}>
          ← 휴지통 목록
        </Link>
      </div>

      <section className={styles.summaryCard}>
        {detailQuery.isPending ? (
          <p className={styles.loading} role="status">
            불러오는 중…
          </p>
        ) : detailQuery.error || !detail ? (
          <p className={styles.errorBox} role="alert">
            쪽지 정보를 불러오지 못했습니다.
          </p>
        ) : (
          <>
            <span className={styles.typeBadge}>{TYPE_LABEL[detail.type]}</span>
            <h1 id="cs-trash-detail-title" className={styles.title}>
              {detail.title}
            </h1>
            <div className={styles.summaryMeta}>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>받는 사용자</span>
                <span className={styles.summaryMetaValue}>
                  {detail.user_email}
                </span>
                {detail.user_name && (
                  <span className={styles.summaryMetaSub}>
                    ({detail.user_name})
                  </span>
                )}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>최초 발송</span>
                {formatKoreanDate(detail.created_at)}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>휴지통 이동</span>
                {formatKoreanDate(detail.deleted_at)}
              </span>
              <span className={styles.summaryMetaItem}>
                <span className={styles.summaryMetaLabel}>읽음 상태</span>
                <span
                  className={`${styles.readStatus} ${
                    detail.is_read
                      ? styles.readStatusRead
                      : styles.readStatusUnread
                  }`}
                >
                  {detail.is_read ? "읽음" : "안 읽음"}
                </span>
              </span>
            </div>

            <div className={styles.purgeBanner} role="status">
              <span className={styles.purgeIcon} aria-hidden="true">
                ⏱
              </span>
              <div className={styles.purgeText}>
                <strong className={styles.purgeStrong}>
                  자동 영구 삭제 예정일 ·{" "}
                  {formatKoreanDateOnly(detail.permanent_purge_at)}
                </strong>
                <span className={styles.purgeHint}>
                  (D-{daysUntilPurge(detail.permanent_purge_at)} · 30일 보관 후
                  배치가 자동으로 영구 삭제합니다)
                </span>
              </div>
            </div>

            <div
              className={styles.body}
              dangerouslySetInnerHTML={{ __html: detail.body_html_safe }}
            />
          </>
        )}
      </section>

      {detail && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.restoreBtn}
            onClick={() => {
              setRestoreError(null);
              setRestoreOpen(true);
            }}
            disabled={busy}
          >
            복구
          </button>
          <button
            type="button"
            className={styles.deleteBtn}
            onClick={() => {
              setDeleteError(null);
              setDeleteOpen(true);
            }}
            disabled={busy}
          >
            영구 삭제
          </button>
        </div>
      )}

      <ConfirmDialog
        open={restoreOpen}
        title="쪽지를 복구할까요?"
        description={
          detail
            ? `"${detail.title}" 쪽지를 ${detail.user_email} 사용자의 쪽지함으로 다시 보냅니다.`
            : ""
        }
        confirmLabel="복구"
        cancelLabel="취소"
        isSubmitting={restoreMutation.isPending}
        errorMessage={restoreError ?? undefined}
        onCancel={() => {
          if (!restoreMutation.isPending) {
            setRestoreOpen(false);
            setRestoreError(null);
          }
        }}
        onConfirm={() => restoreMutation.mutate()}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="영구 삭제할까요?"
        description={
          detail
            ? `"${detail.title}" 쪽지를 즉시 삭제합니다. 이 작업은 되돌릴 수 없습니다.`
            : ""
        }
        confirmLabel="영구 삭제"
        cancelLabel="취소"
        danger
        isSubmitting={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setDeleteOpen(false);
            setDeleteError(null);
          }
        }}
        onConfirm={() => deleteMutation.mutate()}
      />
    </section>
  );
}
