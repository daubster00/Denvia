"use client";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  promptUpdateSchema,
  type PromptUpdateInput,
  type PromptUpdatePayload,
  type TriggerConfig,
  type TriggerMode,
  updatePromptBlock,
} from "../api/prompts";
import type { PromptBlock } from "../api/prompts";
import styles from "./PromptBlockCard.module.css";

interface Props {
  block: PromptBlock;
}

type ListField =
  | "keywords"
  | "keywords_all"
  | "set1"
  | "independent"
  | "group_keywords"
  | "required_keywords";

// 관리자가 고를 수 있는 발동 방식(BASE 제외).
const SELECTABLE_MODES: TriggerMode[] = ["keywords", "keywords_all", "keywords_combo", "group"];

const MODE_LABELS: Record<TriggerMode, string> = {
  base: "항상 포함 (BASE 전용)",
  keywords: "키워드 — 하나라도 일치하면 발동",
  keywords_all: "키워드 — 모두 일치해야 발동",
  keywords_combo: "조합 — 주요어 2개 또는 주요어+보조어",
  group: "그룹 + 필수",
};

// mode 별로 편집할 리스트 필드 + 사람이 읽는 라벨/설명.
const MODE_FIELDS: Record<TriggerMode, { field: ListField; label: string; hint: string }[]> = {
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
const ERROR_MESSAGES: Record<string, string> = {
  PROMPT_TRIGGER_MODE_INVALID: "발동 방식이 올바르지 않아요.",
  PROMPT_TRIGGER_BASE_LOCKED: "BASE 블록의 발동조건은 바꿀 수 없어요.",
  PROMPT_TRIGGER_KEYWORDS_EMPTY: "발동 단어를 하나 이상 입력하세요.",
  PROMPT_TRIGGER_REGEX_INVALID: "패턴 형식이 올바르지 않아요.",
  PROMPT_CONTENT_EMPTY: "내용을 입력하세요.",
  PROMPT_BLOCK_NOT_FOUND: "블록을 찾을 수 없어요.",
};

function listOf(trigger: TriggerConfig, field: ListField): string[] {
  return (trigger as Record<ListField, string[] | undefined>)[field] ?? [];
}

// 저장 직전 정리 — 선택된 mode 에 해당하는 리스트만 남기고 공백/빈 항목 제거.
function cleanTrigger(trigger: TriggerConfig): TriggerConfig {
  if (trigger.mode === "base") return { mode: "base" };
  const out: TriggerConfig = { mode: trigger.mode };
  for (const { field } of MODE_FIELDS[trigger.mode]) {
    (out as Record<ListField, string[]>)[field] = listOf(trigger, field)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return out;
}

function KeywordListEditor({
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

export function PromptBlockCard({ block }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingData, setPendingData] = useState<PromptUpdatePayload | null>(null);
  const queryClient = useQueryClient();

  const isBase = block.block_id === "BASE";

  // 초기 발동조건 — trigger_config 가 없는 구데이터는 keywords 로 폴백.
  const initialTrigger = useMemo<TriggerConfig>(
    () =>
      block.trigger_config ??
      (isBase ? { mode: "base" } : { mode: "keywords", keywords: block.trigger_keywords }),
    [block, isBase],
  );

  const [trigger, setTrigger] = useState<TriggerConfig>(initialTrigger);

  const {
    register,
    handleSubmit,
    reset,
    formState: { isDirty: formDirty, errors },
  } = useForm<PromptUpdateInput>({
    resolver: zodResolver(promptUpdateSchema),
    defaultValues: { content: block.content, enabled: block.enabled },
  });

  const triggerDirty =
    JSON.stringify(cleanTrigger(trigger)) !== JSON.stringify(cleanTrigger(initialTrigger));

  // 저장 가능 조건: 선택 mode 의 필수 리스트가 모두 비어있지 않아야 함(백엔드 검증 미러).
  const triggerValid =
    isBase ||
    MODE_FIELDS[trigger.mode].every(
      ({ field }) => listOf(trigger, field).map((s) => s.trim()).filter(Boolean).length > 0,
    );

  const mutation = useMutation({
    mutationFn: (data: PromptUpdatePayload) => updatePromptBlock(block.block_id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-prompts"] });
      setConfirmOpen(false);
      if (pendingData) {
        reset({ content: pendingData.content, enabled: pendingData.enabled });
        if (pendingData.trigger_config) setTrigger(pendingData.trigger_config);
      }
    },
  });

  const onSubmit = (data: PromptUpdateInput) => {
    const payload: PromptUpdatePayload = {
      content: data.content,
      enabled: data.enabled,
      trigger_config: isBase ? { mode: "base" } : cleanTrigger(trigger),
    };
    setPendingData(payload);
    setConfirmOpen(true);
  };

  const handleConfirm = () => {
    if (pendingData) mutation.mutate(pendingData);
  };

  const handleCancel = () => {
    reset();
    setTrigger(initialTrigger);
  };

  const setListField = (field: ListField, next: string[]) => {
    setTrigger((prev) => ({ ...prev, [field]: next }));
  };

  const mutationErrorMsg =
    mutation.isError && mutation.error instanceof Error
      ? ERROR_MESSAGES[mutation.error.message] ?? "저장 실패"
      : null;

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setExpanded((e) => !e)}
      >
        <span className={styles.blockId}>{block.block_id}</span>
        <span className={styles.chevron}>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <form onSubmit={handleSubmit(onSubmit)} className={styles.body}>
          {/* 발동조건 편집 (#129) */}
          <div className={styles.triggerSection}>
            <div className={styles.triggerHeading}>발동 조건</div>
            {isBase ? (
              <p className={styles.lockedNote}>
                BASE 블록은 모든 답변에 항상 포함돼요. 발동 조건이 없습니다.
              </p>
            ) : (
              <>
                <label className={styles.modeRow}>
                  <span className={styles.modeLabel}>발동 방식</span>
                  <select
                    className={styles.modeSelect}
                    value={trigger.mode}
                    onChange={(e) =>
                      setTrigger((prev) => ({ ...prev, mode: e.target.value as TriggerMode }))
                    }
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

                {!triggerValid && (
                  <p className={styles.error}>발동 단어를 하나 이상 입력하세요.</p>
                )}
              </>
            )}
          </div>

          <label className={styles.enabledLabel}>
            <input type="checkbox" {...register("enabled")} />
            <span>블록 활성화</span>
          </label>

          <div className={styles.triggerHeading}>블록 내용</div>
          <textarea className={styles.textarea} rows={10} {...register("content")} />
          {errors.content && (
            <p className={styles.error}>{errors.content.message}</p>
          )}

          {mutationErrorMsg && <p className={styles.error}>{mutationErrorMsg}</p>}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={handleCancel}
              disabled={!formDirty && !triggerDirty}
            >
              취소
            </button>
            <button
              type="submit"
              className={styles.saveBtn}
              disabled={
                (!formDirty && !triggerDirty) || !triggerValid || mutation.isPending
              }
            >
              {mutation.isPending ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="프롬프트 저장"
        description="저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?"
        confirmLabel="저장"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
