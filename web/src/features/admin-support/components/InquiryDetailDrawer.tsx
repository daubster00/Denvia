"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type {
  InquiryDetailResponse,
  InquiryReplyItem,
  InquiryStatus,
  RecentQAExcerpt,
} from "@/features/admin-support/api/inquiries";
import { InquiryUpdateError } from "@/features/admin-support/api/inquiries";
import {
  formatInquiryStatus,
  formatInquiryType,
  formatSegment,
} from "@/features/admin-support/labels";
import { useUpdateInquiry } from "@/features/admin-support/hooks/useUpdateInquiry";
import { usePostInquiryReply } from "@/features/admin-support/hooks/usePostInquiryReply";
import { StatusRevertConfirmDialog } from "./StatusRevertConfirmDialog";
import styles from "./InquiryDetailDrawer.module.css";

// Tiptap lazy load — Story 7.2 PopupEditDialog 패턴 답습
const RichTextEditor = dynamic(
  () =>
    import("@/components/editor/RichTextEditor").then(
      (m) => m.RichTextEditor,
    ),
  {
    ssr: false,
    loading: () => <p role="status">에디터를 불러오는 중…</p>,
  },
);

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

const STATUS_OPTIONS: InquiryStatus[] = ["open", "in_progress", "resolved"];

const SUBSCRIPTION_STATUS_LABEL: Record<string, string> = {
  free: "무료",
  pro: "Pro",
  blocked: "차단됨",
};

function isEmptyHtml(html: string): boolean {
  return html.replace(/<[^>]*>/g, "").trim().length === 0;
}

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
  const [replyHtml, setReplyHtml] = useState("");
  const [postReplyStatus, setPostReplyStatus] = useState<"resolved" | "in_progress">(
    "resolved",
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [revertCandidate, setRevertCandidate] = useState<InquiryStatus | null>(null);

  const updateMutation = useUpdateInquiry(detail?.id ?? null);
  const replyMutation = usePostInquiryReply(detail?.id ?? null);

  useEffect(() => {
    setReplyHtml("");
    setPostReplyStatus("resolved");
    setFeedback(null);
    setErrorMsg(null);
    setRevertCandidate(null);
  }, [detail?.id]);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && revertCandidate === null) {
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
  }, [open, onClose, revertCandidate]);

  if (!open) return null;

  function executeStatusUpdate(next: InquiryStatus, force: boolean) {
    if (!detail) return;
    setFeedback(null);
    setErrorMsg(null);
    updateMutation.mutate(
      { status: next, force },
      {
        onSuccess: () => {
          setRevertCandidate(null);
          setFeedback(`상태가 "${formatInquiryStatus(next)}"로 변경되었습니다.`);
        },
        onError: (err) => {
          if (
            err instanceof InquiryUpdateError &&
            err.status === 409 &&
            err.code === "INQUIRY_STATUS_REVERT_REQUIRES_CONFIRMATION"
          ) {
            setRevertCandidate(next);
            return;
          }
          setRevertCandidate(null);
          setErrorMsg(err.message ?? "상태 변경에 실패했습니다.");
        },
      },
    );
  }

  function handleStatusSelect(next: InquiryStatus) {
    if (!detail || updateMutation.isPending) return;
    if (next === detail.status) return;
    executeStatusUpdate(next, false);
  }

  function handleRevertConfirm() {
    if (revertCandidate === null) return;
    executeStatusUpdate(revertCandidate, true);
  }

  function handleReplySubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || replyMutation.isPending) return;
    if (isEmptyHtml(replyHtml)) {
      setErrorMsg("답변 본문을 입력해주세요.");
      return;
    }
    setFeedback(null);
    setErrorMsg(null);
    replyMutation.mutate(
      { reply_html: replyHtml, new_status: postReplyStatus },
      {
        onSuccess: () => {
          setReplyHtml("");
          setFeedback("답변이 등록되었고 사용자에게 알림이 발송되었습니다.");
        },
        onError: (err) => {
          setErrorMsg(err.message ?? "답변 등록에 실패했습니다.");
        },
      },
    );
  }

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
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
              <h3 className={styles.subjectTitle}>{detail.subject}</h3>
              <dl className={styles.metaList}>
                <div className={styles.metaRow}>
                  <dt>유형</dt>
                  <dd>{formatInquiryType(detail.inquiry_type)}</dd>
                </div>
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
                  <dt>가입유형</dt>
                  <dd>{formatSegment(detail.user_segment)}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>구독 상태</dt>
                  <dd>
                    {SUBSCRIPTION_STATUS_LABEL[detail.user_subscription_status] ??
                      detail.user_subscription_status}
                  </dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>가입일</dt>
                  <dd>{formatDateTime(detail.user_created_at)}</dd>
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

            {detail.attachments.length > 0 ? (
              <section className={styles.section}>
                <h4 className={styles.sectionLabel}>
                  첨부 이미지 ({detail.attachments.length}장)
                </h4>
                <ul className={styles.attachmentGrid}>
                  {detail.attachments.map((att) => (
                    <li key={att.id} className={styles.attachmentItem}>
                      <a
                        href={att.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.attachmentLink}
                      >
                        <img
                          src={att.file_url}
                          alt={att.file_name}
                          className={styles.attachmentThumb}
                          loading="lazy"
                        />
                        <span className={styles.attachmentName}>
                          {att.file_name}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {detail.replies.length > 0 ? (
              <section className={styles.section}>
                <h4 className={styles.sectionLabel}>
                  답변 이력 ({detail.replies.length}건)
                </h4>
                <ul className={styles.replyList}>
                  {detail.replies.map((reply: InquiryReplyItem) => (
                    <li key={reply.reply_id} className={styles.replyItem}>
                      <p className={styles.replyMeta}>
                        관리자({reply.admin_email_masked}) ·{" "}
                        {formatDateTime(reply.created_at)}
                      </p>
                      <div
                        className={styles.replyContent}
                        // sanitize는 백엔드에서 nh3로 적용 + 응답 직전 재sanitize (이중 방어)
                        dangerouslySetInnerHTML={{ __html: reply.reply_html_safe }}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>사용자 직전 질의 (최대 3건)</h4>
              {detail.recent_qa.length === 0 ? (
                <p className={styles.emptyHint}>최근 질의 이력이 없습니다.</p>
              ) : (
                <ol className={styles.qaList}>
                  {detail.recent_qa.map((qa: RecentQAExcerpt, idx) => (
                    <li key={qa.qa_log_id} className={styles.qaItem}>
                      <span className={styles.qaIndex}>Q{idx + 1}.</span>
                      <span className={styles.qaText}>
                        {qa.question_excerpt} · {formatDateTime(qa.created_at)}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>상태 변경</h4>
              <select
                className={styles.statusSelect}
                value={detail.status}
                onChange={(e) => handleStatusSelect(e.target.value as InquiryStatus)}
                disabled={updateMutation.isPending}
                aria-label="상태 변경"
              >
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {formatInquiryStatus(status)}
                  </option>
                ))}
              </select>
              <p className={styles.helpText}>
                완료된 문의를 되돌릴 때는 한 번 더 확인을 받습니다.
              </p>
            </section>

            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>답변 등록</h4>
              <p className={styles.helpText}>
                서식이 적용된 답변을 등록하면 사용자 쪽지함에 발송되고 알림톡이
                전송됩니다.
              </p>
              <form className={styles.replyForm} onSubmit={handleReplySubmit}>
                <RichTextEditor
                  value={replyHtml}
                  onChange={setReplyHtml}
                  ariaLabel="문의 답변 본문"
                />
                <div className={styles.replyControls}>
                  <label className={styles.replyControlsLabel}>
                    답변 후 상태:
                    <select
                      className={styles.replyStatusSelect}
                      value={postReplyStatus}
                      onChange={(e) =>
                        setPostReplyStatus(
                          e.target.value as "resolved" | "in_progress",
                        )
                      }
                      disabled={replyMutation.isPending}
                    >
                      <option value="resolved">완료(기본)</option>
                      <option value="in_progress">진행 중 유지</option>
                    </select>
                  </label>
                  <button
                    type="submit"
                    className={styles.submitButton}
                    disabled={replyMutation.isPending || isEmptyHtml(replyHtml)}
                  >
                    {replyMutation.isPending ? "전송 중…" : "답변 보내기"}
                  </button>
                </div>
              </form>
            </section>

            {feedback ? (
              <p className={styles.feedback} role="status">
                {feedback}
              </p>
            ) : null}
            {errorMsg ? (
              <p className={styles.error} role="alert">
                {errorMsg}
              </p>
            ) : null}
          </div>
        )}
      </aside>

      <StatusRevertConfirmDialog
        open={revertCandidate !== null && detail !== undefined}
        currentStatus={detail?.status ?? "open"}
        requestedStatus={revertCandidate ?? "open"}
        isPending={updateMutation.isPending}
        onCancel={() => {
          if (!updateMutation.isPending) setRevertCandidate(null);
        }}
        onConfirm={handleRevertConfirm}
      />
    </>
  );
}
