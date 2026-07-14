"use client";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  deletePromptBlock,
  promptUpdateSchema,
  type PromptUpdateInput,
  type PromptUpdatePayload,
  type TriggerConfig,
  updatePromptBlock,
} from "../api/prompts";
import type { PromptBlock } from "../api/prompts";
import {
  cleanTrigger,
  ERROR_MESSAGES,
  SuppressEditor,
  triggerValid,
  TriggerEditor,
} from "./promptTrigger";
import styles from "./PromptBlockCard.module.css";

interface Props {
  block: PromptBlock;
  /** 예외처리 대상 선택용 — 전체 블록 id 목록. */
  allBlockIds: string[];
}

export function PromptBlockCard({ block, allBlockIds }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [pendingData, setPendingData] = useState<PromptUpdatePayload | null>(null);
  const queryClient = useQueryClient();

  const isBase = block.block_id === "BASE";

  const initialSuppresses = useMemo<string[]>(
    () => block.suppresses ?? [],
    [block],
  );
  const [suppresses, setSuppresses] = useState<string[]>(initialSuppresses);

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

  const suppressDirty =
    JSON.stringify([...suppresses].sort()) !== JSON.stringify([...initialSuppresses].sort());

  const dirty = formDirty || triggerDirty || suppressDirty;

  const triggerOk = isBase || triggerValid(trigger);

  const mutation = useMutation({
    mutationFn: (data: PromptUpdatePayload) => updatePromptBlock(block.block_id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-prompts"] });
      setConfirmOpen(false);
      if (pendingData) {
        reset({ content: pendingData.content, enabled: pendingData.enabled });
        if (pendingData.trigger_config) setTrigger(pendingData.trigger_config);
        setSuppresses(pendingData.suppresses ?? []);
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deletePromptBlock(block.block_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-prompts"] });
      setDeleteConfirmOpen(false);
    },
  });

  const onSubmit = (data: PromptUpdateInput) => {
    const payload: PromptUpdatePayload = {
      content: data.content,
      enabled: data.enabled,
      trigger_config: isBase ? { mode: "base" } : cleanTrigger(trigger),
      suppresses: isBase ? [] : suppresses,
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
    setSuppresses(initialSuppresses);
  };

  const mutationErrorMsg =
    mutation.isError && mutation.error instanceof Error
      ? ERROR_MESSAGES[mutation.error.message] ?? "저장 실패"
      : null;

  const deleteErrorMsg =
    deleteMutation.isError && deleteMutation.error instanceof Error
      ? ERROR_MESSAGES[deleteMutation.error.message] ?? "삭제 실패"
      : null;

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setExpanded((e) => !e)}
      >
        <span className={styles.blockId}>
          {block.block_id}
          {!block.enabled && <span className={styles.offBadge}>꺼짐</span>}
        </span>
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
              <TriggerEditor trigger={trigger} setTrigger={setTrigger} />
            )}
          </div>

          {!isBase && (
            <div className={styles.triggerSection}>
              <div className={styles.triggerHeading}>예외처리 (상호배제)</div>
              <SuppressEditor
                allBlockIds={allBlockIds}
                selfId={block.block_id}
                value={suppresses}
                onChange={setSuppresses}
              />
            </div>
          )}

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
          {deleteErrorMsg && <p className={styles.error}>{deleteErrorMsg}</p>}

          <div className={styles.actions}>
            {block.deletable && (
              <button
                type="button"
                className={styles.deleteBtn}
                onClick={() => setDeleteConfirmOpen(true)}
                disabled={deleteMutation.isPending}
              >
                블록 삭제
              </button>
            )}
            <span className={styles.actionsSpacer} />
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={handleCancel}
              disabled={!dirty}
            >
              취소
            </button>
            <button
              type="submit"
              className={styles.saveBtn}
              disabled={!dirty || !triggerOk || mutation.isPending}
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

      <ConfirmDialog
        open={deleteConfirmOpen}
        title="블록 삭제"
        description={`'${block.block_id}' 블록을 완전히 삭제합니다. 이 블록은 모든 신규 답변에서 즉시 사라지며 되돌릴 수 없습니다. 진행하시겠습니까?`}
        confirmLabel="삭제"
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </div>
  );
}
