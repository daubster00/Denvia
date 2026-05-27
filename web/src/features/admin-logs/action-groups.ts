/**
 * Story 10.4 — 액션 코드 그룹 7종 + 색상 매핑.
 *
 * `ACTION_GROUPS` 는 그룹화 칩 UI의 SSOT.
 * 백엔드에 그룹 → 액션 코드 expansion 엔드포인트가 없으므로,
 * 본 모듈이 그룹별 prefix 를 보유하고 프론트에서 expand 한다.
 *
 * 그룹화 칩 ON/OFF 는 `getSelectedActions(groupKeys, knownCatalog)` 로
 * 백엔드로 보낼 `action_in[]` 을 만든다.
 */

export type ActionGroupKey =
  | "admin-accounts"
  | "user-management"
  | "notice-dm"
  | "popup"
  | "cs-refund"
  | "rag-prompt"
  | "ops-settings";

export interface ActionGroup {
  key: ActionGroupKey;
  label: string;
  chipColor: string;
  prefixes: string[];
}

export const ACTION_GROUPS: ActionGroup[] = [
  {
    key: "admin-accounts",
    label: "관리자 계정",
    chipColor: "#7c3aed",
    prefixes: [
      "admin.account.",
      "admin.master.",
      "admin.auth.",
      "admin.grade_permission.",
    ],
  },
  {
    key: "user-management",
    label: "사용자 관리",
    chipColor: "#2563eb",
    prefixes: ["user."],
  },
  {
    key: "notice-dm",
    label: "공지·쪽지",
    chipColor: "#0891b2",
    prefixes: ["notice.", "admin_dm.", "inbox_preview_config."],
  },
  {
    key: "popup",
    label: "팝업",
    chipColor: "#db2777",
    prefixes: ["popup."],
  },
  {
    key: "cs-refund",
    label: "CS·환불",
    chipColor: "#ea580c",
    prefixes: ["support.", "refund."],
  },
  {
    key: "rag-prompt",
    label: "RAG·프롬프트",
    chipColor: "#16a34a",
    prefixes: ["rag.", "prompt."],
  },
  {
    key: "ops-settings",
    label: "운영 설정",
    chipColor: "#6b7280",
    prefixes: [
      "killswitch.",
      "anomaly.",
      "anomaly_throttle_config.",
      "runtime_config.",
      "budget.",
      "seo_config.",
      "login_brute_threshold.",
    ],
  },
];

export function getActionGroupForCode(action: string): ActionGroupKey | null {
  for (const group of ACTION_GROUPS) {
    if (group.prefixes.some((prefix) => action.startsWith(prefix))) {
      return group.key;
    }
  }
  return null;
}

export function chipColorForAction(action: string): string {
  const key = getActionGroupForCode(action);
  if (!key) return "#9ca3af"; // 기본 회색
  return ACTION_GROUPS.find((g) => g.key === key)?.chipColor ?? "#9ca3af";
}

/**
 * 선택된 그룹 키들 + 액션 코드 카탈로그를 받아,
 * 백엔드 `action_in[]` 쿼리에 보낼 실제 액션 코드 리스트를 만든다.
 *
 * `actionCatalog`은 SSOT(`ACTION_LABELS` 키 집합) 를 넘긴다 — 현재 페이지에 보이는
 * 액션만 넘기면, 그 그룹에 속하지만 아직 한 번도 안 나온 액션은 필터에서 누락되어
 * "필터 ↔ 리스트 불일치" 가 발생한다.
 */
export function expandGroupsToActions(
  groupKeys: ActionGroupKey[],
  actionCatalog: string[],
): string[] {
  if (groupKeys.length === 0) return [];
  const groups = ACTION_GROUPS.filter((g) => groupKeys.includes(g.key));
  const out = new Set<string>();
  for (const action of actionCatalog) {
    if (
      groups.some((g) =>
        g.prefixes.some((prefix) => action.startsWith(prefix)),
      )
    ) {
      out.add(action);
    }
  }
  return Array.from(out);
}
