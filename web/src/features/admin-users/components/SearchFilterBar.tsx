"use client";

import {
  type ChangeEvent,
  type KeyboardEvent,
  useEffect,
  useState,
} from "react";
import type {
  Segment,
  SubscriptionStatus,
} from "@/features/admin-users/api/users";
import { useDebouncedValue } from "@/features/admin-users/hooks/useDebouncedValue";
import styles from "./SearchFilterBar.module.css";

export interface SearchFilters {
  q: string;
  segment: Segment | null;
  subscription_status: SubscriptionStatus | null;
  blocked: boolean | null;
}

interface Props {
  value: SearchFilters;
  onChange: (next: SearchFilters) => void;
  onReset: () => void;
  onRefresh: () => void;
  isFetching?: boolean;
}

const SEGMENT_OPTIONS: { value: Segment | "all"; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "dentist", label: "치과의사" },
  { value: "dental_hygienist", label: "치과위생사" },
  { value: "student_other", label: "학생/기타" },
];

const STATUS_OPTIONS: { value: SubscriptionStatus | "all"; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "free", label: "무료" },
  { value: "pro", label: "Pro" },
  { value: "blocked", label: "차단" },
];

const BLOCKED_OPTIONS: { value: "all" | "true" | "false"; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "true", label: "차단만" },
  { value: "false", label: "차단 외" },
];

export function SearchFilterBar({
  value,
  onChange,
  onReset,
  onRefresh,
  isFetching = false,
}: Props) {
  const [localQ, setLocalQ] = useState(value.q);
  const debouncedQ = useDebouncedValue(localQ, 300);

  // 외부 value.q 동기화 (초기화 등)
  useEffect(() => {
    setLocalQ(value.q);
  }, [value.q]);

  // 디바운스된 q를 부모로 push (입력값과 다를 때만)
  useEffect(() => {
    if (debouncedQ !== value.q) {
      onChange({ ...value, q: debouncedQ });
    }
    // value.q가 외부에서 변하는 경우 무한 루프 방지를 위해 onChange는 의존성에서 제외
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQ]);

  function handleEnter(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onChange({ ...value, q: localQ });
    }
  }

  function handleSegmentChange(event: ChangeEvent<HTMLSelectElement>) {
    const v = event.target.value;
    onChange({ ...value, segment: v === "all" ? null : (v as Segment) });
  }

  function handleStatusChange(event: ChangeEvent<HTMLSelectElement>) {
    const v = event.target.value;
    onChange({
      ...value,
      subscription_status: v === "all" ? null : (v as SubscriptionStatus),
    });
  }

  function handleBlockedChange(event: ChangeEvent<HTMLSelectElement>) {
    const v = event.target.value;
    onChange({
      ...value,
      blocked: v === "all" ? null : v === "true",
    });
  }

  return (
    <div
      className={styles.bar}
      role="group"
      aria-label="검색 필터"
    >
      <input
        type="search"
        className={styles.search}
        value={localQ}
        onChange={(e) => setLocalQ(e.target.value)}
        onKeyDown={handleEnter}
        placeholder="이메일·휴대폰·카드 뒷4자리로 검색"
        aria-label="사용자 통합 검색"
      />

      <select
        className={styles.select}
        value={value.segment ?? "all"}
        onChange={handleSegmentChange}
        aria-label="가입유형 필터"
      >
        {SEGMENT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <select
        className={styles.select}
        value={value.subscription_status ?? "all"}
        onChange={handleStatusChange}
        aria-label="구독 상태 필터"
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <select
        className={styles.select}
        value={value.blocked === null ? "all" : String(value.blocked)}
        onChange={handleBlockedChange}
        aria-label="차단 여부 필터"
      >
        {BLOCKED_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        className={styles.resetButton}
        onClick={onReset}
        aria-label="검색 조건 초기화"
      >
        초기화
      </button>

      <button
        type="button"
        className={styles.refreshButton}
        onClick={onRefresh}
        aria-label="검색 결과 새로고침"
        disabled={isFetching}
      >
        ↻ 새로고침
      </button>
    </div>
  );
}
