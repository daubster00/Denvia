"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchUserAnomalyEvents,
  fetchUserInquiries,
  fetchUserQALogs,
  type PagedResponse,
  type UserAnomalyEventItem,
  type UserInquiryItem,
  type UserQALogItem,
} from "@/features/admin-users/api/activity";
import {
  fetchAuditLogs,
  type AuditLogItem,
  type AuditLogListResponse,
} from "@/features/admin-users/api/audit";
import {
  fetchPaymentEvents,
  type PaymentEventItem,
  type PaymentEventListResponse,
} from "@/features/admin-finance/api/payments";
import {
  formatAnomalyType,
  formatAuditAction,
  formatDiffField,
} from "@/features/admin-users/labels";
import styles from "./UserActivityLogs.module.css";

interface Props {
  userId: number;
}

type TabKey = "qa" | "inquiry" | "payment" | "anomaly" | "audit";

const PER_PAGE = 20;

const TABS: { key: TabKey; label: string }[] = [
  { key: "qa", label: "질의" },
  { key: "inquiry", label: "문의" },
  { key: "payment", label: "결제 이벤트" },
  { key: "anomaly", label: "이상 이벤트" },
  { key: "audit", label: "권한 변경 이력" },
];

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function fmt(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

function inquiryStatusClass(status: string): string {
  if (status === "open") return styles.chipOpen;
  if (status === "in_progress") return styles.chipInProgress;
  if (status === "resolved") return styles.chipResolved;
  return styles.chip;
}

function inquiryStatusLabel(status: string): string {
  if (status === "open") return "미처리";
  if (status === "in_progress") return "처리 중";
  if (status === "resolved") return "완료";
  return status;
}

function anomalyStatusClass(status: string): string {
  if (status === "new") return styles.chipAnomalyNew;
  if (status === "actioned") return styles.chipAnomalyActioned;
  return styles.chip;
}

function paymentStatusClass(status: string): string {
  if (status === "success") return styles.chipPaymentSuccess;
  if (status === "failed") return styles.chipPaymentFailed;
  if (status === "refunded" || status === "refund_pending") {
    return styles.chipPaymentRefunded;
  }
  return styles.chip;
}

function paymentStatusLabel(status: string): string {
  if (status === "success") return "성공";
  if (status === "failed") return "실패";
  if (status === "pending") return "대기";
  if (status === "refunded") return "환불 완료";
  if (status === "refund_pending") return "환불 대기";
  return status;
}

function paymentEventTypeLabel(eventType: string): string {
  switch (eventType) {
    case "charge_requested":
      return "결제 요청";
    case "charge_success":
      return "결제 성공";
    case "charge_failed":
      return "결제 실패";
    case "retry_scheduled":
      return "재시도 예약";
    case "refund_requested":
      return "환불 요청";
    case "refund_success":
      return "환불 완료";
    case "refund_denied":
      return "환불 거부";
    default:
      return eventType;
  }
}

function summarizeAuditDiff(
  diff: Record<string, unknown> | null,
): string {
  if (!diff) return "—";
  const before = (diff.before ?? {}) as Record<string, unknown>;
  const after = (diff.after ?? {}) as Record<string, unknown>;
  const keys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  );
  if (keys.length === 0) return "—";
  return keys.map(formatDiffField).join(", ");
}

interface PaginationProps {
  page: number;
  total: number;
  perPage: number;
  onChange: (next: number) => void;
}

function Pagination({ page, total, perPage, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  if (totalPages <= 1) return null;
  return (
    <nav className={styles.pagination} aria-label="페이지네이션">
      <button
        type="button"
        className={styles.pageButton}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        이전
      </button>
      <span className={styles.pageInfo}>
        {page} / {totalPages}
      </span>
      <button
        type="button"
        className={styles.pageButton}
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        다음
      </button>
    </nav>
  );
}

interface PanelState<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
}

function PanelChrome({
  state,
  emptyText,
  children,
}: {
  state: PanelState<unknown>;
  emptyText: string;
  children: React.ReactNode;
}) {
  if (state.isError) {
    return (
      <div className={styles.error} role="alert">
        불러오지 못했습니다. 잠시 후 다시 시도해주세요.
      </div>
    );
  }
  if (state.isLoading && state.data === undefined) {
    return (
      <div className={styles.loading} role="status">
        불러오는 중...
      </div>
    );
  }
  return <>{children}</>;
}

function QATab({ userId }: { userId: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery<PagedResponse<UserQALogItem>>({
    queryKey: ["admin", "users", userId, "qa-logs", page],
    queryFn: () => fetchUserQALogs({ userId, page, perPage: PER_PAGE }),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const items = query.data?.items ?? [];
  return (
    <PanelChrome state={query} emptyText="질의 기록이 없습니다.">
      {items.length === 0 ? (
        <p className={styles.empty}>질의 기록이 없습니다.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table} data-testid="user-qa-logs-table">
            <thead>
              <tr>
                <th>일시</th>
                <th>질문</th>
                <th>입력/출력</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.qa_log_id}>
                  <td className={styles.muted}>{fmt(row.created_at)}</td>
                  <td className={styles.cellQuestion}>
                    {row.question_excerpt || "—"}
                  </td>
                  <td className={styles.muted}>
                    {row.input_tokens ?? "—"} / {row.output_tokens ?? "—"}
                  </td>
                  <td>
                    <span className={styles.chip}>{row.status ?? "—"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        perPage={PER_PAGE}
        onChange={setPage}
      />
    </PanelChrome>
  );
}

function InquiryTab({ userId }: { userId: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery<PagedResponse<UserInquiryItem>>({
    queryKey: ["admin", "users", userId, "inquiries", page],
    queryFn: () => fetchUserInquiries({ userId, page, perPage: PER_PAGE }),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const items = query.data?.items ?? [];
  return (
    <PanelChrome state={query} emptyText="문의 내역이 없습니다.">
      {items.length === 0 ? (
        <p className={styles.empty}>문의 내역이 없습니다.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table} data-testid="user-inquiries-table">
            <thead>
              <tr>
                <th>일시</th>
                <th>제목</th>
                <th>본문</th>
                <th>상태</th>
                <th>처리</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td className={styles.muted}>{fmt(row.created_at)}</td>
                  <td className={styles.cellSubject}>{row.subject}</td>
                  <td className={styles.cellPreview}>
                    {row.body_preview || "—"}
                  </td>
                  <td>
                    <span className={inquiryStatusClass(row.status)}>
                      {inquiryStatusLabel(row.status)}
                    </span>
                  </td>
                  <td className={styles.muted}>{fmt(row.resolved_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        perPage={PER_PAGE}
        onChange={setPage}
      />
    </PanelChrome>
  );
}

function PaymentTab({ userId }: { userId: number }) {
  const [page, setPage] = useState(1);
  // 최대 5년 — Story 9.1 retention 정책에 맞춰 1825일 lookback.
  const today = new Date();
  const to = today.toISOString().slice(0, 10);
  const fromDate = new Date(today);
  fromDate.setDate(fromDate.getDate() - 1825);
  const from = fromDate.toISOString().slice(0, 10);

  const query = useQuery<PaymentEventListResponse>({
    queryKey: ["admin", "users", userId, "payment-events", page, from, to],
    queryFn: () =>
      fetchPaymentEvents({
        user_id: userId,
        from,
        to,
        page,
        per_page: 50,
      }),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const items: PaymentEventItem[] = query.data?.items ?? [];
  return (
    <PanelChrome state={query} emptyText="결제 이벤트가 없습니다.">
      {items.length === 0 ? (
        <p className={styles.empty}>결제 이벤트가 없습니다.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table
            className={styles.table}
            data-testid="user-payment-events-table"
          >
            <thead>
              <tr>
                <th>일시</th>
                <th>이벤트</th>
                <th>금액</th>
                <th>카드</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.event_id}>
                  <td className={styles.muted}>{fmt(row.charged_at)}</td>
                  <td>{paymentEventTypeLabel(row.event_type)}</td>
                  <td>{row.amount_krw.toLocaleString("ko-KR")}원</td>
                  <td className={styles.muted}>
                    {row.card_company ?? "—"} {row.card_last4 ?? ""}
                  </td>
                  <td>
                    <span className={paymentStatusClass(row.status)}>
                      {paymentStatusLabel(row.status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        perPage={50}
        onChange={setPage}
      />
    </PanelChrome>
  );
}

function AnomalyTab({ userId }: { userId: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery<PagedResponse<UserAnomalyEventItem>>({
    queryKey: ["admin", "users", userId, "anomaly-events", page],
    queryFn: () =>
      fetchUserAnomalyEvents({ userId, page, perPage: PER_PAGE }),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const items = query.data?.items ?? [];
  return (
    <PanelChrome state={query} emptyText="이상 이벤트가 없습니다.">
      {items.length === 0 ? (
        <p className={styles.empty}>이상 이벤트가 없습니다.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table
            className={styles.table}
            data-testid="user-anomaly-events-table"
          >
            <thead>
              <tr>
                <th>일시</th>
                <th>유형</th>
                <th>IP</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td className={styles.muted}>{fmt(row.created_at)}</td>
                  <td>{formatAnomalyType(row.type)}</td>
                  <td className={styles.mono}>{row.ip ?? "—"}</td>
                  <td>
                    <span className={anomalyStatusClass(row.status)}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        perPage={PER_PAGE}
        onChange={setPage}
      />
    </PanelChrome>
  );
}

function AuditTab({ userId }: { userId: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery<AuditLogListResponse>({
    queryKey: ["admin", "users", userId, "audit-logs", page],
    queryFn: () =>
      fetchAuditLogs({ target_id: userId, page, per_page: PER_PAGE }),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const items: AuditLogItem[] = query.data?.items ?? [];
  return (
    <PanelChrome state={query} emptyText="권한 변경 이력이 없습니다.">
      {items.length === 0 ? (
        <p className={styles.empty}>권한 변경 이력이 없습니다.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table} data-testid="user-audit-logs-table">
            <thead>
              <tr>
                <th>일시</th>
                <th>액션</th>
                <th>변경 필드</th>
                <th>관리자</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const isSystem = row.action === "user.block_auto_expired";
                return (
                  <tr key={row.id}>
                    <td className={styles.muted}>{fmt(row.created_at)}</td>
                    <td>{formatAuditAction(row.action)}</td>
                    <td className={styles.diffSummary}>
                      {summarizeAuditDiff(row.diff_json)}
                    </td>
                    <td className={styles.muted}>
                      {isSystem
                        ? "시스템 자동"
                        : row.actor_email ?? `(ID ${row.actor_user_id})`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        perPage={PER_PAGE}
        onChange={setPage}
      />
    </PanelChrome>
  );
}

export function UserActivityLogs({ userId }: Props) {
  const [tab, setTab] = useState<TabKey>("qa");

  return (
    <div className={styles.root} data-testid="user-activity-logs">
      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ""}`}
            onClick={() => setTab(t.key)}
            data-testid={`tab-${t.key}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className={styles.panel} role="tabpanel">
        {tab === "qa" ? <QATab userId={userId} /> : null}
        {tab === "inquiry" ? <InquiryTab userId={userId} /> : null}
        {tab === "payment" ? <PaymentTab userId={userId} /> : null}
        {tab === "anomaly" ? <AnomalyTab userId={userId} /> : null}
        {tab === "audit" ? <AuditTab userId={userId} /> : null}
      </div>
    </div>
  );
}
