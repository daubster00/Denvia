"use client";

/**
 * Story 10.4 — `/admin/admins/logs` 활동 로그 페이지.
 *
 * - 필터 4종: 관리자 드롭다운 / 기간 / 액션 코드 그룹 / target_id
 * - 무한 스크롤 (IntersectionObserver, 100건 단위)
 * - "엑셀로 저장" — 최대 10,000행, X-Truncated 시 토스트 노출
 * - 행별 펼치기 → diff_json REDACTED 마스킹 + JSON 트리 뷰
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AdminLogsApiError,
  fetchLogs,
  triggerExport,
  type AdminLogFilters,
  type AdminLogItem,
} from "@/features/admin-logs/api";
import {
  ACTION_GROUPS,
  getActionGroupForCode,
  expandGroupsToActions,
  type ActionGroupKey,
} from "@/features/admin-logs/action-groups";
import { ACTION_LABELS } from "@/features/admin-logs/action-labels";
import { LogRow } from "./LogRow";
import styles from "./page.module.css";

// SSOT 액션 카탈로그 — 그룹 칩 → action_in 확장은 현재 페이지가 아니라 본 목록 기준.
// 본 목록에 없는 백엔드 신규 액션은 ACTION_LABELS 에 추가하면 자동 반영된다.
const ACTION_CATALOG = Object.keys(ACTION_LABELS);
// 그룹이 선택됐는데 매칭 액션이 0개일 때, 백엔드가 action_in 미설정으로 해석해
// "전체 통과" 가 되지 않도록 보내는 sentinel. 실제 코드와 절대 겹치지 않는 문자열.
const NO_MATCH_SENTINEL = "__no_action_match__";

const PAGE_LIMIT = 100;
const DEFAULT_RANGE_DAYS = 7;

function _toIsoUtcFromKstDate(dateStr: string, endOfDay: boolean): string {
  // dateStr: "YYYY-MM-DD" — KST 자정/23:59:59 → UTC ISO
  const [y, m, d] = dateStr.split("-").map(Number);
  const utcHours = endOfDay ? 14 + 9 : 0; // KST 자정 = UTC 15:00 전날 / 23:59:59 KST = 14:59:59 UTC
  // 명료하게 — KST = UTC + 9h.
  // KST 00:00:00 = UTC 전날 15:00:00. 단순화 위해 그냥 KST 시각을 UTC로 -9h offset 직접 계산.
  const kstMs = Date.UTC(y, m - 1, d, endOfDay ? 23 : 0, endOfDay ? 59 : 0, endOfDay ? 59 : 0);
  const utcMs = kstMs - 9 * 60 * 60 * 1000;
  return new Date(utcMs).toISOString();
}

function _todayKstDateStr(): string {
  const now = new Date();
  // KST = UTC + 9
  const kstMs = now.getTime() + 9 * 60 * 60 * 1000;
  const kst = new Date(kstMs);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(kst.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function _daysAgoKstDateStr(days: number): string {
  const now = new Date();
  const kstMs = now.getTime() + 9 * 60 * 60 * 1000 - days * 24 * 60 * 60 * 1000;
  const kst = new Date(kstMs);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(kst.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function AdminLogsPage() {
  // 필터 상태
  const [actorIdInput, setActorIdInput] = useState<string>(""); // "", "system", "<int>"
  const [groupKeys, setGroupKeys] = useState<ActionGroupKey[]>([]);
  const [fromDate, setFromDate] = useState<string>(
    _daysAgoKstDateStr(DEFAULT_RANGE_DAYS - 1),
  );
  const [toDate, setToDate] = useState<string>(_todayKstDateStr());
  const [targetIdInput, setTargetIdInput] = useState<string>("");

  // 페이지 상태
  const [items, setItems] = useState<AdminLogItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [toast, setToast] = useState<
    { kind: "info" | "error" | "warn"; text: string } | null
  >(null);

  const buildFilters = useCallback(
    (cursor: string | null): AdminLogFilters => {
      const filters: AdminLogFilters = { limit: PAGE_LIMIT };
      if (actorIdInput) {
        if (actorIdInput === "system") {
          filters.actor_id = "system";
        } else {
          const n = parseInt(actorIdInput, 10);
          if (!Number.isNaN(n)) filters.actor_id = n;
        }
      }
      if (fromDate) filters.from_at = _toIsoUtcFromKstDate(fromDate, false);
      if (toDate) filters.to_at = _toIsoUtcFromKstDate(toDate, true);
      if (targetIdInput) {
        const n = parseInt(targetIdInput, 10);
        if (!Number.isNaN(n)) filters.target_id = n;
      }
      if (groupKeys.length > 0) {
        const expanded = expandGroupsToActions(groupKeys, ACTION_CATALOG);
        // 그룹이 선택된 이상 항상 action_in 을 전송한다. 빈 결과면 sentinel 로
        // 백엔드가 "전체 패스" 로 해석하지 않게 한다.
        filters.action_in = expanded.length > 0 ? expanded : [NO_MATCH_SENTINEL];
      }
      if (cursor) filters.cursor = cursor;
      return filters;
    },
    [actorIdInput, fromDate, toDate, targetIdInput, groupKeys],
  );

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLogs(buildFilters(null));
      setItems(res.items);
      setNextCursor(res.next_cursor);
    } catch (e) {
      const msg =
        e instanceof AdminLogsApiError
          ? `${e.message} (${e.code})`
          : "로그를 불러오지 못했습니다.";
      setToast({ kind: "error", text: msg });
    } finally {
      setLoading(false);
    }
  }, [buildFilters]);

  const loadNextPage = useCallback(async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await fetchLogs(buildFilters(nextCursor));
      setItems((prev) => [...prev, ...res.items]);
      setNextCursor(res.next_cursor);
    } catch (e) {
      const msg =
        e instanceof AdminLogsApiError
          ? `${e.message} (${e.code})`
          : "다음 페이지 로딩에 실패했습니다.";
      setToast({ kind: "error", text: msg });
    } finally {
      setLoadingMore(false);
    }
  }, [nextCursor, loadingMore, buildFilters]);

  // 초기 로드 (마운트 시 1회)
  useEffect(() => {
    void loadFirstPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 무한 스크롤 sentinel
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && nextCursor && !loadingMore) {
            void loadNextPage();
          }
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [nextCursor, loadingMore, loadNextPage]);

  const handleApply = () => {
    void loadFirstPage();
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const { truncated } = await triggerExport(buildFilters(null));
      if (truncated) {
        setToast({
          kind: "warn",
          text: "최근 10,000행만 다운로드되었습니다. 기간을 좁혀 다시 시도해주세요.",
        });
      } else {
        setToast({ kind: "info", text: "엑셀 다운로드를 시작했습니다." });
      }
    } catch (e) {
      const msg =
        e instanceof AdminLogsApiError
          ? `${e.message} (${e.code})`
          : "엑셀 다운로드에 실패했습니다.";
      setToast({ kind: "error", text: msg });
    } finally {
      setExporting(false);
    }
  };

  const toggleGroup = (key: ActionGroupKey) => {
    setGroupKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 활동 로그</h1>
        <p className={styles.caption}>
          관리자 콘솔에서 일어난 작업의 타임라인을 조회합니다. (시스템 자동 액션은 첫 admin
          계정으로 기록됩니다.)
        </p>
      </header>

      <section className={styles.filterCard}>
        <div className={styles.filterRow}>
          <label className={styles.filterLabel} htmlFor="actor-id">
            관리자 ID
          </label>
          <input
            id="actor-id"
            className={`${styles.fieldInput} ${styles.fieldInputNarrow}`}
            placeholder="숫자 또는 system"
            value={actorIdInput}
            onChange={(e) => setActorIdInput(e.target.value.trim())}
          />
          <label className={styles.filterLabel} htmlFor="from-date">
            기간
          </label>
          <input
            id="from-date"
            type="date"
            className={`${styles.fieldInput} ${styles.fieldInputNarrow}`}
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
          <span>~</span>
          <input
            type="date"
            className={`${styles.fieldInput} ${styles.fieldInputNarrow}`}
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
          <label className={styles.filterLabel} htmlFor="target-id">
            대상 ID
          </label>
          <input
            id="target-id"
            className={`${styles.fieldInput} ${styles.fieldInputNarrow}`}
            placeholder="target_id"
            value={targetIdInput}
            onChange={(e) => setTargetIdInput(e.target.value.trim())}
          />
        </div>

        <div className={styles.filterRow}>
          <span className={styles.filterLabel}>액션 코드</span>
          <div className={styles.actionChips}>
            {ACTION_GROUPS.map((group) => {
              const active = groupKeys.includes(group.key);
              return (
                <button
                  type="button"
                  key={group.key}
                  className={`${styles.chip} ${active ? styles.chipActive : ""}`}
                  data-group-key={group.key}
                  data-active={active}
                  onClick={() => toggleGroup(group.key)}
                >
                  {group.label}
                </button>
              );
            })}
            <button
              type="button"
              className={styles.chipLink}
              onClick={() => setGroupKeys(ACTION_GROUPS.map((g) => g.key))}
            >
              전체 선택
            </button>
            <button
              type="button"
              className={styles.chipLink}
              onClick={() => setGroupKeys([])}
            >
              해제
            </button>
          </div>
        </div>

        <div className={styles.applyRow}>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={() => void handleExport()}
            disabled={exporting || loading}
          >
            {exporting ? "다운로드 중..." : "엑셀로 저장"}
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={handleApply}
            disabled={loading}
          >
            {loading ? "조회 중..." : "필터 적용"}
          </button>
        </div>
      </section>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>시각 (KST)</th>
              <th>Actor</th>
              <th>액션 코드</th>
              <th>Target</th>
              <th>IP</th>
              <th>변경 내역</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className={styles.emptyState}>
                  조회된 로그가 없습니다.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <LogRow
                key={item.id}
                item={item}
                groupKey={getActionGroupForCode(item.action)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {nextCursor && (
        <div ref={sentinelRef} className={styles.sentinel}>
          {loadingMore ? "다음 페이지 로드 중..." : "스크롤하면 다음 페이지가 로드됩니다."}
        </div>
      )}

      <div className={styles.footnote}>
        시스템 자동 액션(예: 차단 자동 만료)은 첫 admin 계정 ID로 기록되므로 actor 표시가 시스템과
        구분되지 않을 수 있습니다.
      </div>

      {toast && (
        <div
          className={`${styles.toast} ${
            toast.kind === "error"
              ? styles.toastError
              : toast.kind === "warn"
                ? styles.toastWarn
                : ""
          }`}
          onClick={() => setToast(null)}
          role="status"
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}
