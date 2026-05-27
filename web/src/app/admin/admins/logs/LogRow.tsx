"use client";

/**
 * Story 10.4 — 활동 로그 한 행 (확장 가능한 diff viewer 포함).
 *
 * 펼치기 클릭 시 `fetchLogDiff(id)` 호출 → REDACTED 마스킹된 JSON 트리 뷰 렌더.
 */

import { useCallback, useMemo, useState } from "react";
import {
  AdminLogsApiError,
  fetchLogDiff,
  type AdminLogItem,
} from "@/features/admin-logs/api";
import type { ActionGroupKey } from "@/features/admin-logs/action-groups";
import { labelForAction } from "@/features/admin-logs/action-labels";
import { formatDiff } from "@/features/admin-logs/diff-format";
import styles from "./page.module.css";

interface Props {
  item: AdminLogItem;
  groupKey: ActionGroupKey | null;
}

function _utcIsoToKstDisplay(iso: string): string {
  // ISO 8601 UTC → KST "YYYY-MM-DD HH:mm:ss"
  const utc = new Date(iso);
  if (Number.isNaN(utc.getTime())) return iso;
  const kstMs = utc.getTime() + 9 * 60 * 60 * 1000;
  const k = new Date(kstMs);
  const yyyy = k.getUTCFullYear();
  const mm = String(k.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(k.getUTCDate()).padStart(2, "0");
  const hh = String(k.getUTCHours()).padStart(2, "0");
  const mi = String(k.getUTCMinutes()).padStart(2, "0");
  const ss = String(k.getUTCSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

function _renderDiffJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function LogRow({ item, groupKey }: Props) {
  const [expanded, setExpanded] = useState<boolean>(false);
  const [diff, setDiff] = useState<unknown>(null);
  const [diffLoading, setDiffLoading] = useState<boolean>(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState<boolean>(false);

  const onToggle = useCallback(async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (!item.has_diff) {
      setExpanded(true);
      return;
    }
    if (diff !== null) {
      setExpanded(true);
      return;
    }
    setDiffLoading(true);
    setDiffError(null);
    try {
      const res = await fetchLogDiff(item.id);
      setDiff(res.diff_json);
      setExpanded(true);
    } catch (e) {
      const msg =
        e instanceof AdminLogsApiError
          ? `${e.message} (${e.code})`
          : "변경 내역을 불러오지 못했습니다.";
      setDiffError(msg);
      setExpanded(true);
    } finally {
      setDiffLoading(false);
    }
  }, [expanded, item.has_diff, item.id, diff]);

  const targetDisplay = item.target_type
    ? item.target_preview
      ? `${item.target_type} #${item.target_id} — ${item.target_preview}`
      : `${item.target_type}${item.target_id !== null ? ` #${item.target_id}` : ""}`
    : "—";

  const diffText =
    diff !== null && diff !== undefined ? _renderDiffJson(diff) : "";

  const descriptionLines = useMemo(
    () => (diff !== null && diff !== undefined ? formatDiff(item.action, diff) : []),
    [diff, item.action],
  );

  return (
    <>
      <tr>
        <td>{_utcIsoToKstDisplay(item.created_at)}</td>
        <td>
          <span title={`ID #${item.actor_user_id}`}>
            {item.actor_email || `#${item.actor_user_id}`}
          </span>
        </td>
        <td>
          <span
            className={styles.actionChip}
            data-group-key={groupKey ?? ""}
            title={item.action}
          >
            {labelForAction(item.action)}
          </span>
        </td>
        <td>{targetDisplay}</td>
        <td className={styles.muted}>{item.ip ?? "—"}</td>
        <td>
          <button
            type="button"
            className={styles.diffBtn}
            onClick={() => void onToggle()}
            disabled={diffLoading}
          >
            {diffLoading ? "..." : expanded ? "접기" : item.has_diff ? "펼치기" : "본문 없음"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className={styles.diffRow}>
          <td colSpan={6} className={styles.diffCell}>
            {diffError ? (
              <div className={styles.errorState}>{diffError}</div>
            ) : !item.has_diff ? (
              <div className={styles.muted}>변경 내역이 없습니다.</div>
            ) : descriptionLines.length === 0 ? (
              <div className={styles.muted}>
                요약할 변경 내역이 없습니다. 아래 원본 데이터를 확인하세요.
              </div>
            ) : (
              <ul className={styles.descList}>
                {descriptionLines.map((line, i) => (
                  <li key={i} className={styles.descItem}>
                    <span className={styles.descLabel}>{line.label}</span>
                    {line.value !== undefined ? (
                      <span className={styles.descValue}>{line.value}</span>
                    ) : (
                      <span className={styles.descValue}>
                        <span className={styles.descBefore}>
                          {line.before ?? "(없음)"}
                        </span>
                        <span className={styles.descArrow}>→</span>
                        <span className={styles.descAfter}>
                          {line.after ?? "(없음)"}
                        </span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {item.has_diff && !diffError && (
              <div className={styles.rawToggleWrap}>
                <button
                  type="button"
                  className={styles.rawToggleBtn}
                  onClick={() => setShowRaw((v) => !v)}
                >
                  {showRaw ? "원본 데이터 숨기기 ▲" : "원본 데이터 보기 ▼"}
                </button>
                {showRaw && (
                  <pre className={styles.diffPre}>
                    {diffText.split("***REDACTED***").map((chunk, i, arr) => (
                      <span key={i}>
                        {chunk}
                        {i < arr.length - 1 && (
                          <span className={styles.redacted}>***REDACTED***</span>
                        )}
                      </span>
                    ))}
                  </pre>
                )}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
