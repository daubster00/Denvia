"use client";

import { useRouter } from "next/navigation";
import { formatKRW } from "@/lib/format-currency";
import { UserTokensRow } from "../api/analytics";
import styles from "./UserTokensTable.module.css";

interface Props {
  items: UserTokensRow[];
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function UserTokensTable({
  items,
  page,
  perPage,
  total,
  onPageChange,
}: Props) {
  const router = useRouter();
  const totalPages = Math.ceil(total / perPage);
  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);

  if (items.length === 0) {
    return (
      <div className={styles.empty}>
        이번 기간에 질의 기록이 없습니다.
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">이메일</th>
              <th scope="col">세그먼트</th>
              <th scope="col">입력 토큰</th>
              <th scope="col">출력 토큰</th>
              <th scope="col">총 비용</th>
              <th scope="col">질의 수</th>
              <th scope="col">평균 비용</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr
                key={row.user_id}
                className={styles.clickableRow}
                onClick={() => router.push(`/admin/users/${row.user_id}`)}
              >
                <td>{row.email}</td>
                <td>{row.segment ?? "—"}</td>
                <td>{row.total_input_tokens.toLocaleString()}</td>
                <td>{row.total_output_tokens.toLocaleString()}</td>
                <td>{formatKRW(row.total_cost_krw)}</td>
                <td>{row.question_count}</td>
                <td>{formatKRW(row.avg_cost_per_question_krw)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <span className={styles.paginationInfo}>
          {total > 0 ? `${start}–${end} / 총 ${total}명` : "0건"}
        </span>
        <div className={styles.paginationButtons}>
          <button
            className={styles.pageBtn}
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            aria-label="이전 페이지"
          >
            ◀
          </button>
          <span className={styles.pageIndicator}>
            {page} / {totalPages}
          </span>
          <button
            className={styles.pageBtn}
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            aria-label="다음 페이지"
          >
            ▶
          </button>
        </div>
      </div>
    </div>
  );
}
