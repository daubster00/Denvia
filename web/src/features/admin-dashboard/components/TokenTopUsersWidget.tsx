"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchUserTokens, type UserTokensRow } from "../api/analytics";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./TokenTopUsersWidget.module.css";

const TOP_N = 5;

const QUERY_KEY = [
  "admin",
  "dashboard",
  "user-tokens-top",
  { range: "month", per_page: TOP_N },
] as const;

const ROW_DISABLED_TITLE = "사용자 상세는 Epic 6에서 제공됩니다";

export function TokenTopUsersWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => fetchUserTokens({ range: "month", per_page: TOP_N }),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="사용자별 토큰 비용 TOP 5"
      caption="이번 달 비용이 높은 사용자 5명을 표시합니다."
      detailHref="/admin/dashboard/token-breakdown"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <WidgetEmptyState message="이번 기간에 질의 기록이 없습니다." />
      )}
      {data && data.items.length > 0 && <TopUsersList items={data.items} />}
    </DashboardWidget>
  );
}

function TopUsersList({ items }: { items: UserTokensRow[] }) {
  const maxCost = items.reduce(
    (acc, row) => Math.max(acc, Number(row.total_cost_usd)),
    0,
  );

  return (
    <ol className={styles.list}>
      {items.map((row, idx) => {
        const cost = Number(row.total_cost_usd);
        const widthPct =
          maxCost > 0 ? Math.max(Math.min((cost / maxCost) * 100, 100), 4) : 0;
        const tokens = row.total_input_tokens + row.total_output_tokens;
        return (
          <li
            key={row.user_id}
            className={`${styles.row} ${styles.rowDisabled}`}
            title={ROW_DISABLED_TITLE}
            data-disabled="true"
          >
            <span className={styles.rank} aria-label={`${idx + 1}위`}>
              {idx + 1}
            </span>
            <div className={styles.email}>
              <span>{row.email}</span>
              <div
                className={styles.barTrack}
                role="progressbar"
                aria-valuenow={Math.round((cost / Math.max(maxCost, 1)) * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${row.email} 비용 비율`}
              >
                <div
                  className={styles.barFill}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            </div>
            <span className={styles.muted}>
              {row.question_count.toLocaleString()}건
            </span>
            <div className={styles.metrics}>
              <span className={styles.cost}>$ {cost.toFixed(4)}</span>
              <span className={styles.muted}>
                {tokens.toLocaleString()} tok
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
