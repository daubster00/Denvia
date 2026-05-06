"use client";

import { useEffect, useRef, useState } from "react";
import type {
  InquiryDetailResponse,
  InquiryStatus,
} from "@/features/admin-support/api/inquiries";
import { formatInquiryStatus } from "@/features/admin-support/labels";
import { useUpdateInquiry } from "@/features/admin-support/hooks/useUpdateInquiry";
import styles from "./InquiryDetailDrawer.module.css";

interface Props {
  open: boolean;
  detail: InquiryDetailResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
  onRetry: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

function badgeClassFor(status: string): string {
  if (status === "resolved") return styles.badgeResolved;
  if (status === "in_progress") return styles.badgeProgress;
  return styles.badgeOpen;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input, select, textarea';

const STATUS_TRANSITIONS: InquiryStatus[] = ["open", "in_progress", "resolved"];

export function InquiryDetailDrawer({
  open,
  detail,
  isLoading,
  isError,
  onClose,
  onRetry,
}: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [reply, setReply] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  const mutation = useUpdateInquiry(detail?.id ?? null);

  useEffect(() => {
    setReply("");
    setFeedback(null);
  }, [detail?.id]);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && drawerRef.current) {
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
          FOCUSABLE_SELECTOR,
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  function handleStatusChange(next: InquiryStatus) {
    if (!detail || mutation.isPending) return;
    setFeedback(null);
    mutation.mutate(
      { status: next },
      {
        onSuccess: () => setFeedback(`상태가 "${formatInquiryStatus(next)}"로 변경되었습니다.`),
        onError: (err) => setFeedback(err.message ?? "상태 변경에 실패했습니다."),
      },
    );
  }

  function handleReplySubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || mutation.isPending) return;
    const trimmed = reply.trim();
    if (trimmed.length === 0) {
      setFeedback("답변 내용을 입력해주세요.");
      return;
    }
    setFeedback(null);
    mutation.mutate(
      { reply_message: trimmed },
      {
        onSuccess: () => {
          setReply("");
          setFeedback("답변이 등록되었고 사용자 알림함에 발송되었습니다.");
        },
        onError: (err) => setFeedback(err.message ?? "답변 등록에 실패했습니다."),
      },
    );
  }

  return (
    <>
      <div
        className={styles.backdrop}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={drawerRef}
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-detail-title"
      >
        <header className={styles.header}>
          <h2 id="inquiry-detail-title" className={styles.title}>
            문의 상세
          </h2>
          <button
            type="button"
            ref={closeBtnRef}
            className={styles.closeButton}
            onClick={onClose}
            aria-label="닫기"
          >
            ×
          </button>
        </header>

        {isError ? (
          <div className={styles.errorBox} role="alert">
            <p className={styles.errorText}>문의 정보를 불러오지 못했습니다.</p>
            <button type="button" className={styles.retryButton} onClick={onRetry}>
              다시 시도
            </button>
          </div>
        ) : isLoading || !detail ? (
          <div className={styles.loadingBox} aria-busy="true">
            <p>불러오는 중…</p>
          </div>
        ) : (
          <div className={styles.body}>
            <section className={styles.section}>
              <h3 className={styles.sectionTitle}>{detail.subject}</h3>
              <dl className={styles.metaList}>
                <div className={styles.metaRow}>
                  <dt>상태</dt>
                  <dd>
                    <span className={badgeClassFor(detail.status)}>
                      {formatInquiryStatus(detail.status)}
                    </span>
                  </dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>사용자</dt>
                  <dd>
                    {detail.user_email}
                    {detail.user_phone ? ` · ${detail.user_phone}` : ""}
                  </dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>접수일</dt>
                  <dd>{formatDateTime(detail.created_at)}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>완료일</dt>
                  <dd>{formatDateTime(detail.resolved_at)}</dd>
                </div>
              </dl>
            </section>

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>문의 내용</h4>
              <pre className={styles.bodyText}>{detail.body}</pre>
            </section>

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>상태 변경</h4>
              <div className={styles.statusActions}>
                {STATUS_TRANSITIONS.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={
                      status === detail.status
                        ? `${styles.statusButton} ${styles.statusButtonActive}`
                        : styles.statusButton
                    }
                    onClick={() => handleStatusChange(status)}
                    disabled={mutation.isPending || status === detail.status}
                  >
                    {formatInquiryStatus(status)}
                  </button>
                ))}
              </div>
            </section>

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>답변 등록</h4>
              <p className={styles.helpText}>
                답변을 등록하면 사용자 알림함에 메시지가 발송되고 상태가 자동으로
                완료 처리됩니다.
              </p>
              <form className={styles.replyForm} onSubmit={handleReplySubmit}>
                <textarea
                  className={styles.replyTextarea}
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="답변 내용을 입력해주세요 (최대 5000자)"
                  maxLength={5000}
                  rows={6}
                  disabled={mutation.isPending}
                  aria-label="답변 본문"
                />
                <div className={styles.replyFooter}>
                  <span className={styles.charCount}>
                    {reply.length} / 5000
                  </span>
                  <button
                    type="submit"
                    className={styles.submitButton}
                    disabled={mutation.isPending || reply.trim().length === 0}
                  >
                    {mutation.isPending ? "전송 중…" : "답변 보내기"}
                  </button>
                </div>
              </form>
            </section>

            {feedback ? (
              <p className={styles.feedback} role="status">
                {feedback}
              </p>
            ) : null}
          </div>
        )}
      </aside>
    </>
  );
}
