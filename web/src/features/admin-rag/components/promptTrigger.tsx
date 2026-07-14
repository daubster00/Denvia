"use client";
// 프롬프트 발동조건(트리거) 편집 공유 로직 — PromptBlockCard(수정)와 NewPromptBlockForm(생성)에서 함께 사용.
import { useState } from "react";
import type { TriggerConfig, TriggerMode } from "../api/prompts";
import styles from "./PromptBlockCard.module.css";

export type ListField =
  | "keywords"
  | "keywords_all"
  | "set1"
  | "independent"
  | "group_keywords"
  | "required_keywords";

// 관리자가 고를 수 있는 발동 방식(BASE 제외).
export const SELECTABLE_MODES: TriggerMode[] = [
  "keywords",
  "keywords_all",
  "keywords_combo",
  "group",
];

export const MODE_LABELS: Record<TriggerMode, string> = {
  base: "항상 포함 (BASE 전용)",
  keywords: "키워드 — 하나라도 일치하면 발동",
  keywords_all: "키워드 — 모두 일치해야 발동",
  keywords_combo: "조합 — 주요어 2개 또는 주요어+보조어",
  group: "그룹 + 필수",
};

// mode 별로 편집할 리스트 필드 + 사람이 읽는 라벨/설명.
export const MODE_FIELDS: Record<
  TriggerMode,
  { field: ListField; label: string; hint: string }[]
> = {
  base: [],
  keywords: [
    { field: "keywords", label: "발동 키워드", hint: "이 중 하나라도 질문에 있으면 규칙이 켜져요." },
  ],
  keywords_all: [
    { field: "keywords_all", label: "발동 키워드", hint: "이 단어들이 질문에 모두 있어야 켜져요." },
  ],
  keywords_combo: [
    { field: "set1", label: "주요 단어", hint: "이 중 2개 이상이면 켜져요." },
    { field: "independent", label: "보조 단어", hint: "주요 단어 1개 + 보조 단어 1개 조합이어도 켜져요." },
  ],
  group: [
    { field: "group_keywords", label: "그룹 단어", hint: "이 중 하나 이상." },
    { field: "required_keywords", label: "필수 단어", hint: "그룹 단어와 함께 이 중 하나 이상 있어야 켜져요." },
  ],
};

// 백엔드 검증 코드 → 사람이 읽는 메시지.
export const ERROR_MESSAGES: Record<string, string> = {
  PROMPT_TRIGGER_MODE_INVALID: "발동 방식이 올바르지 않아요.",
  PROMPT_TRIGGER_BASE_LOCKED: "BASE 블록의 발동조건은 바꿀 수 없어요.",
  PROMPT_TRIGGER_KEYWORDS_EMPTY: "발동 단어를 하나 이상 입력하세요.",
  PROMPT_TRIGGER_REGEX_INVALID: "패턴 형식이 올바르지 않아요.",
  PROMPT_TRIGGER_REQUIRED: "발동 조건을 입력하세요.",
  PROMPT_CONTENT_EMPTY: "내용을 입력하세요.",
  PROMPT_BLOCK_NOT_FOUND: "블록을 찾을 수 없어요.",
  PROMPT_BLOCK_ID_EMPTY: "블록 이름을 입력하세요.",
  PROMPT_BLOCK_ID_TOO_LONG: "블록 이름이 너무 길어요. (최대 40자)",
  PROMPT_BLOCK_ID_RESERVED: "사용할 수 없는 이름이에요. (예약어 또는 ':' 포함)",
  PROMPT_BLOCK_ID_DUPLICATE: "이미 같은 이름의 블록이 있어요.",
  PROMPT_BLOCK_BUILTIN_UNDELETABLE: "원본 블록은 삭제할 수 없어요. 끄기만 가능해요.",
};

export function listOf(trigger: TriggerConfig, field: ListField): string[] {
  return (trigger as Record<ListField, string[] | undefined>)[field] ?? [];
}

// 저장 직전 정리 — 선택된 mode 에 해당하는 리스트만 남기고 공백/빈 항목 제거.
export function cleanTrigger(trigger: TriggerConfig): TriggerConfig {
  if (trigger.mode === "base") return { mode: "base" };
  const out: TriggerConfig = { mode: trigger.mode };
  for (const { field } of MODE_FIELDS[trigger.mode]) {
    (out as Record<ListField, string[]>)[field] = listOf(trigger, field)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return out;
}

// 저장 가능 조건: 선택 mode 의 필수 리스트가 모두 비어있지 않아야 함(백엔드 검증 미러).
export function triggerValid(trigger: TriggerConfig): boolean {
  if (trigger.mode === "base") return true;
  return MODE_FIELDS[trigger.mode].every(
    ({ field }) => listOf(trigger, field).map((s) => s.trim()).filter(Boolean).length > 0,
  );
}

export function KeywordListEditor({
  label,
  hint,
  values,
  onChange,
}: {
  label: string;
  hint: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const t = draft.trim();
    if (!t || values.includes(t)) {
      setDraft("");
      return;
    }
    onChange([...values, t]);
    setDraft("");
  };

  return (
    <div className={styles.triggerField}>
      <div className={styles.triggerLabel}>{label}</div>
      <div className={styles.triggerHint}>{hint}</div>
      <div className={styles.keywords}>
        {values.length === 0 && <span className={styles.emptyNote}>단어 없음</span>}
        {values.map((kw) => (
          <span key={kw} className={styles.chipEditable}>
            {kw}
            <button
              type="button"
              className={styles.chipRemove}
              aria-label={`${kw} 삭제`}
              onClick={() => onChange(values.filter((k) => k !== kw))}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className={styles.addRow}>
        <input
          type="text"
          className={styles.addInput}
          value={draft}
          placeholder="단어 입력 후 Enter"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className={styles.addBtn} onClick={add}>
          추가
        </button>
      </div>
    </div>
  );
}

/** 예외처리(상호배제) — 이 블록이 켜지면 함께 숨길 다른 블록을 체크로 선택. */
export function SuppressEditor({
  allBlockIds,
  selfId,
  value,
  onChange,
}: {
  allBlockIds: string[];
  selfId: string | null;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  // BASE 는 항상 포함되므로 숨김 대상이 될 수 없고, 자기 자신도 후보에서 제외.
  const candidates = allBlockIds.filter((b) => b !== "BASE" && b !== selfId);
  const toggle = (id: string) => {
    if (value.includes(id)) onChange(value.filter((v) => v !== id));
    else onChange([...value, id]);
  };
  return (
    <div className={styles.triggerField}>
      <div className={styles.triggerHint}>
        이 블록이 켜질 때 함께 숨길 다른 블록을 선택하세요. (아무것도 선택하지 않으면 숨기지 않아요)
      </div>
      <div className={styles.suppressList}>
        {candidates.length === 0 && (
          <span className={styles.emptyNote}>선택할 수 있는 블록이 없어요</span>
        )}
        {candidates.map((id) => (
          <label key={id} className={styles.suppressItem}>
            <input
              type="checkbox"
              checked={value.includes(id)}
              onChange={() => toggle(id)}
            />
            <span>{id}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

/** 발동 방식 선택 + mode 별 키워드 리스트 편집 (BASE 제외). */
export function TriggerEditor({
  trigger,
  setTrigger,
}: {
  trigger: TriggerConfig;
  setTrigger: (next: TriggerConfig) => void;
}) {
  const setListField = (field: ListField, next: string[]) =>
    setTrigger({ ...trigger, [field]: next });

  return (
    <>
      <label className={styles.modeRow}>
        <span className={styles.modeLabel}>발동 방식</span>
        <select
          className={styles.modeSelect}
          value={trigger.mode}
          onChange={(e) => setTrigger({ ...trigger, mode: e.target.value as TriggerMode })}
        >
          {SELECTABLE_MODES.map((m) => (
            <option key={m} value={m}>
              {MODE_LABELS[m]}
            </option>
          ))}
        </select>
      </label>

      {MODE_FIELDS[trigger.mode].map(({ field, label, hint }) => (
        <KeywordListEditor
          key={field}
          label={label}
          hint={hint}
          values={listOf(trigger, field)}
          onChange={(next) => setListField(field, next)}
        />
      ))}

      {!triggerValid(trigger) && (
        <p className={styles.error}>발동 단어를 하나 이상 입력하세요.</p>
      )}
    </>
  );
}
