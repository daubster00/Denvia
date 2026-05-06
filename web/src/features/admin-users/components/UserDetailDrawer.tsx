"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { UserDetailResponse } from "@/features/admin-users/api/users";
import {
  formatAnomalyType,
  formatSegment,
  formatSubscriptionStatus,
} from "@/features/admin-users/labels";
import { UserPermissionDialog } from "./UserPermissionDialog";
import styles from "./UserDetailDrawer.module.css";

interface Props {
  open: boolean;
  detail: UserDetailResponse | undefined;
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

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input, select, textarea';

export function UserDetailDrawer({
  open,
  detail,
  isLoading,
  isError,
  onClose,
  onRetry,
}: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);

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

  const user = detail?.user;
  const subscription = detail?.subscription_summary;
  const isWithdrawn = user?.withdrawn_at !== null && user?.withdrawn_at !== undefined;

  return (
    <>
      <button
        type="button"
        aria-label="닫기"
        className={styles.overlay}
        onClick={onClose}
        tabIndex={-1}
      />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-detail-title"
        className={styles.drawer}
        data-testid="user-detail-drawer"
      >
        <header className={styles.header}>
          <h2 id="user-detail-title" className={styles.title}>
            사용자 상세
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Drawer 닫기"
            className={styles.closeButton}
          >
            ✕
          </button>
        </header>

        {isError ? (
          <div className={styles.errorBox} role="alert">
            <p>상세 정보를 불러오지 못했습니다.</p>
            <button type="button" onClick={onRetry} className={styles.retryButton}>
              다시 시도
            </button>
          </div>
        ) : isLoading || !detail || !user ? (
          <div className={styles.loadingBox} role="status">
            불러오는 중...
          </div>
        ) : (
          <>
            <section className={styles.section} aria-labelledby="basic-info-title">
              <h3 id="basic-info-title" className={styles.sectionTitle}>
                기본 정보
              </h3>
              <dl className={styles.infoList}>
                <div className={styles.infoRow}>
                  <dt>이메일</dt>
                  <dd>{user.email}</dd>
                </div>
                <div className={styles.infoRow}>
                  <dt>휴대폰</dt>
                  <dd>{user.phone ?? "—"}</dd>
                </div>
                <div className={styles.infoRow}>
                  <dt>가입유형</dt>
                  <dd>{formatSegment(user.segment)}</dd>
                </div>
                <div className={styles.infoRow}>
                  <dt>연차</dt>
                  <dd>
                    {user.years_of_experience !== null
                      ? `${user.years_of_experience}년`
                      : "—"}
                  </dd>
                </div>
                <div className={styles.infoRow}>
                  <dt>가입일</dt>
                  <dd>{formatDateTime(user.created_at)}</dd>
                </div>
                <div className={styles.infoRow}>
                  <dt>상태</dt>
                  <dd>
                    <span
                      className={
                        user.subscription_status === "blocked"
                          ? styles.chipBlocked
                          : user.subscription_status === "pro"
                            ? styles.chipPro
                            : styles.chipFree
                      }
                    >
                      {formatSubscriptionStatus(user.subscription_status)}
                    </span>
                    {isWithdrawn ? (
                      <span className={styles.chipWithdrawn}>탈퇴</span>
                    ) : null}
                  </dd>
                </div>
              </dl>
            </section>

            {!isWithdrawn ? (
              <section
                className={styles.section}
                aria-labelledby="subscription-info-title"
              >
                <h3 id="subscription-info-title" className={styles.sectionTitle}>
                  결제 정보
                </h3>
                {subscription && subscription.billing_key_active ? (
                  <dl className={styles.infoList}>
                    <div className={styles.infoRow}>
                      <dt>활성 빌링키</dt>
                      <dd>
                        {subscription.card_company ?? "카드"}{" "}
                        {subscription.card_last4 ?? "—"}
                      </dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>구독 상태</dt>
                      <dd>{formatSubscriptionStatus(subscription.current_status)}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>구독 시작</dt>
                      <dd>{formatDateTime(subscription.subscription_started_at)}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>다음 결제</dt>
                      <dd>{formatDateTime(subscription.next_charge_at)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className={styles.placeholderText}>
                    PG 연동 후 표시됩니다.
                  </p>
                )}
              </section>
            ) : null}

            <section className={styles.section} aria-labelledby="recent-qa-title">
              <h3 id="recent-qa-title" className={styles.sectionTitle}>
                최근 질의 ({detail.recent_qa.length}건)
              </h3>
              {detail.recent_qa.length === 0 ? (
                <p className={styles.placeholderText}>최근 질의가 없습니다.</p>
              ) : (
                <ul className={styles.qaList}>
                  {detail.recent_qa.map((qa) => (
                    <li key={qa.qa_log_id} className={styles.qaItem}>
                      <div className={styles.qaMeta}>
                        <span>{formatDateTime(qa.created_at)}</span>
                        <span>
                          입력 {qa.input_tokens ?? "—"} · 출력 {qa.output_tokens ?? "—"}
                        </span>
                      </div>
                      <p className={styles.qaText}>{qa.question_excerpt}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className={styles.section} aria-labelledby="anomaly-title">
              <h3 id="anomaly-title" className={styles.sectionTitle}>
                최근 이상 이벤트 ({detail.recent_anomaly_events.length}건)
              </h3>
              {detail.recent_anomaly_events.length === 0 ? (
                <p className={styles.placeholderText}>이상 이벤트가 없습니다.</p>
              ) : (
                <ul className={styles.anomalyList}>
                  {detail.recent_anomaly_events.map((event) => (
                    <li key={event.id} className={styles.anomalyItem}>
                      <div className={styles.anomalyHeader}>
                        <span>{formatDateTime(event.created_at)}</span>
                        <span className={styles.anomalyType}>
                          {formatAnomalyType(event.type)}
                        </span>
                      </div>
                      <span className={styles.anomalyIp}>{event.ip ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <footer className={styles.footer}>
              <button
                type="button"
                disabled={isWithdrawn}
                title={
                  isWithdrawn ? "탈퇴 사용자는 권한 변경 불가" : undefined
                }
                onClick={() => setPermissionDialogOpen(true)}
                data-testid="open-permission-dialog"
                className={styles.actionButton}
              >
                권한 수정
              </button>
              {isWithdrawn ? (
                <button
                  type="button"
                  disabled
                  title="탈퇴 사용자는 이력 조회 불가"
                  className={styles.actionButton}
                >
                  이력 보기
                </button>
              ) : (
                <Link
                  href={`/admin/users/edits?user_id=${user.user_id}`}
                  className={styles.actionLink}
                >
                  이력 보기
                </Link>
              )}
            </footer>
          </>
        )}
      </aside>
      <UserPermissionDialog
        open={permissionDialogOpen}
        user={detail?.user}
        onClose={() => setPermissionDialogOpen(false)}
      />
    </>
  );
}
