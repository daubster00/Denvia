"use client";
// #132 — 부관리자별 조회 설정(조회기간 + 볼 수 있는 평가필터) 편집 표. master/operator 전용.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchQaReviewAdminSettings,
  updateQaReviewAdminSetting,
  type QaRatingFilter,
  type QaReviewAdminSettingRow,
} from "../api";
import styles from "./QaReviewAdminSettings.module.css";

const ADMIN_SETTINGS_KEY = ["admin", "qa-review", "admin-settings"] as const;

const LOOKBACK_CHOICES: { value: number | null; label: string }[] = [
  { value: null, label: "전역 기본값" },
  { value: 1, label: "당일" },
  { value: 3, label: "3일" },
  { value: 7, label: "7일" },
  { value: 30, label: "한달" },
];

const SCOPE_CHOICES: { value: QaRatingFilter; label: string }[] = [
  { value: "all", label: "전체보기" },
  { value: "good", label: "굿만" },
  { value: "bad", label: "베드만" },
  { value: "unrated", label: "미평가만" },
];

function daysLabel(days: number): string {
  return days <= 1 ? "당일" : `${days}일`;
}

function AdminRow({
  row,
  globalDays,
}: {
  row: QaReviewAdminSettingRow;
  globalDays: number;
}) {
  const qc = useQueryClient();
  const [days, setDays] = useState<number | null>(row.max_lookback_days);
  const [scope, setScope] = useState<QaRatingFilter>(row.rating_scope);

  const dirty = days !== row.max_lookback_days || scope !== row.rating_scope;

  const mutation = useMutation({
    mutationFn: () =>
      updateQaReviewAdminSetting(row.admin_id, {
        max_lookback_days: days,
        rating_scope: scope,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ADMIN_SETTINGS_KEY }),
  });

  return (
    <tr>
      <td className={styles.emailCell}>
        <span className={styles.email}>{row.email ?? `#${row.admin_id}`}</span>
        {row.admin_grade && <span className={styles.grade}>{row.admin_grade}</span>}
      </td>
      <td>
        <select
          className={styles.select}
          value={days === null ? "" : String(days)}
          onChange={(e) => setDays(e.target.value === "" ? null : Number(e.target.value))}
          aria-label={`${row.email ?? row.admin_id} 조회기간`}
        >
          {LOOKBACK_CHOICES.map((c) => (
            <option key={String(c.value)} value={c.value === null ? "" : String(c.value)}>
              {c.label}
              {c.value === null ? ` (${daysLabel(globalDays)})` : ""}
            </option>
          ))}
        </select>
      </td>
      <td>
        <select
          className={styles.select}
          value={scope}
          onChange={(e) => setScope(e.target.value as QaRatingFilter)}
          aria-label={`${row.email ?? row.admin_id} 볼 수 있는 평가`}
        >
          {SCOPE_CHOICES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </td>
      <td className={styles.actionCell}>
        <button
          type="button"
          className={styles.saveBtn}
          disabled={!dirty || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "저장 중…" : "저장"}
        </button>
        {mutation.isError && <span className={styles.err}>실패</span>}
      </td>
    </tr>
  );
}

export function QaReviewAdminSettings() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ADMIN_SETTINGS_KEY,
    queryFn: fetchQaReviewAdminSettings,
    staleTime: 30_000,
  });

  if (isLoading) return <p className={styles.note}>부관리자 설정을 불러오는 중…</p>;
  if (isError || !data)
    return <p className={styles.note}>부관리자 설정을 불러오지 못했습니다.</p>;
  if (data.admins.length === 0)
    return <p className={styles.note}>설정할 부관리자 계정이 없습니다.</p>;

  return (
    <div className={styles.wrap}>
      <p className={styles.hint}>
        초대된 부관리자별로 조회기간과 볼 수 있는 평가(전체/굿/베드/미평가)를 각각 지정합니다.
        조회기간을 “전역 기본값”으로 두면 위 공통 설정({daysLabel(data.global_default_days)})을
        따릅니다.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">부관리자</th>
              <th scope="col">조회기간</th>
              <th scope="col">볼 수 있는 평가</th>
              <th scope="col" aria-label="저장" />
            </tr>
          </thead>
          <tbody>
            {data.admins.map((row) => (
              <AdminRow key={row.admin_id} row={row} globalDays={data.global_default_days} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
