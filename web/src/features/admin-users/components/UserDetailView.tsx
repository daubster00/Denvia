"use client";

import { useState } from "react";
import Link from "next/link";
import { type UserDetailResponse } from "@/features/admin-users/api/users";
import {
  formatAnomalyType,
  formatSegment,
  formatSubscriptionStatus,
} from "@/features/admin-users/labels";
import { UserPermissionDialog } from "./UserPermissionDialog";
import { UserActivityLogs } from "./UserActivityLogs";
import styles from "./UserDetailView.module.css";

interface Props {
  detail: UserDetailResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPermissionUpdated?: () => void;
}

// rapid_followup_questions actioned 행만 거른 이상탐지 페이지 링크.
const ANOMALY_THROTTLE_LIST_URL =
  "/admin/anomaly?type=rapid_followup_questions&status=actioned";

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const KST_DATE = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    // birthdate 는 YYYY-MM-DD 문자열 — Date 파싱 시 UTC 0시로 해석되어 KST 변환이 어긋날 수 있어 그대로 표시.
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    return KST_DATE.format(new Date(value));
  } catch {
    return value;
  }
}

function formatGender(value: string | null | undefined): string {
  if (value === "male") return "남";
  if (value === "female") return "여";
  return "—";
}

function formatAddress(
  postcode: string | null | undefined,
  road: string | null | undefined,
  detail: string | null | undefined,
): string {
  const parts = [
    postcode ? `(${postcode})` : "",
    road ?? "",
    detail ?? "",
  ].filter((s) => s);
  return parts.length ? parts.join(" ") : "—";
}

export function UserDetailView({
  detail,
  isLoading,
  isError,
  onRetry,
  onPermissionUpdated,
}: Props) {
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        <p>상세 정보를 불러오지 못했습니다.</p>
        <button type="button" onClick={onRetry} className={styles.retryButton}>
          다시 시도
        </button>
      </div>
    );
  }

  if (isLoading || !detail) {
    return (
      <div className={styles.loadingBox} role="status">
        불러오는 중...
      </div>
    );
  }

  const user = detail.user;
  const subscription = detail.subscription_summary;
  const isWithdrawn = user.withdrawn_at !== null && user.withdrawn_at !== undefined;
  const isAnomalyThrottled = Boolean(user.anomaly_throttled_at);

  return (
    <div className={styles.root} data-testid="user-detail-view">
      <div className={styles.grid}>
        <section className={styles.section} aria-labelledby="basic-info-title">
          <h2 id="basic-info-title" className={styles.sectionTitle}>
            기본 정보
          </h2>
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
            {isAnomalyThrottled ? (
              <div className={styles.infoRow}>
                <dt>속도 제한</dt>
                <dd className={styles.throttleCell}>
                  <span className={styles.chipBlocked}>이상탐지 적용 중</span>
                  <span className={styles.throttleSince}>
                    {formatDateTime(user.anomaly_throttled_at ?? null)}
                  </span>
                  <Link
                    href={ANOMALY_THROTTLE_LIST_URL}
                    className={styles.throttleLink}
                  >
                    이상탐지에서 해제
                  </Link>
                </dd>
              </div>
            ) : null}
          </dl>
        </section>

        <section
          className={styles.section}
          aria-labelledby="extra-info-title"
        >
          <h2 id="extra-info-title" className={styles.sectionTitle}>
            추가 정보
          </h2>
          <dl className={styles.infoList}>
            <div className={styles.infoRow}>
              <dt>이름</dt>
              <dd>{user.name ?? "—"}</dd>
            </div>
            <div className={styles.infoRow}>
              <dt>성별</dt>
              <dd>{formatGender(user.gender)}</dd>
            </div>
            <div className={styles.infoRow}>
              <dt>생년월일</dt>
              <dd>{formatDate(user.birthdate)}</dd>
            </div>
            <div className={styles.infoRow}>
              <dt>주소</dt>
              <dd>
                {formatAddress(
                  user.postcode,
                  user.address_road,
                  user.address_detail,
                )}
              </dd>
            </div>
            <div className={styles.infoRow}>
              <dt>마케팅 수신</dt>
              <dd>
                {user.marketing_consent_at
                  ? `동의 (${formatDateTime(user.marketing_consent_at)})`
                  : "미동의"}
              </dd>
            </div>
            <div className={styles.infoRow}>
              <dt>최근 로그인</dt>
              <dd>{formatDateTime(user.last_login_at)}</dd>
            </div>
          </dl>
        </section>

        {!isWithdrawn ? (
          <section
            className={styles.section}
            aria-labelledby="subscription-info-title"
          >
            <h2 id="subscription-info-title" className={styles.sectionTitle}>
              결제 정보
            </h2>
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
                결제 정보가 없습니다.
              </p>
            )}
          </section>
        ) : null}

        <section
          className={`${styles.section} ${styles.sectionFull}`}
          aria-labelledby="anomaly-title"
        >
          <h2 id="anomaly-title" className={styles.sectionTitle}>
            최근 이상 이벤트 ({detail.recent_anomaly_events.length}건)
          </h2>
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

        <section
          className={`${styles.section} ${styles.sectionFull}`}
          aria-labelledby="activity-logs-title"
        >
          <h2 id="activity-logs-title" className={styles.sectionTitle}>
            로그 기록
          </h2>
          {isWithdrawn ? (
            <p className={styles.placeholderText}>
              탈퇴 사용자는 로그 조회 불가
            </p>
          ) : (
            <UserActivityLogs userId={user.user_id} />
          )}
        </section>
      </div>

      <div className={styles.actions}>
        <button
          type="button"
          disabled={isWithdrawn}
          title={isWithdrawn ? "탈퇴 사용자는 권한 변경 불가" : undefined}
          onClick={() => setPermissionDialogOpen(true)}
          data-testid="open-permission-dialog"
          className={styles.actionButton}
        >
          권한 수정
        </button>
      </div>

      <UserPermissionDialog
        open={permissionDialogOpen}
        user={user}
        onClose={() => setPermissionDialogOpen(false)}
        onSuccess={onPermissionUpdated}
      />
    </div>
  );
}
