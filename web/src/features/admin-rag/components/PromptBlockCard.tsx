"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  promptUpdateSchema,
  type PromptUpdateInput,
  updatePromptBlock,
} from "../api/prompts";
import type { PromptBlock } from "../api/prompts";
import styles from "./PromptBlockCard.module.css";

interface Props {
  block: PromptBlock;
}

export function PromptBlockCard({ block }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingData, setPendingData] = useState<PromptUpdateInput | null>(null);
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { isDirty, errors },
  } = useForm<PromptUpdateInput>({
    resolver: zodResolver(promptUpdateSchema),
    defaultValues: { content: block.content, enabled: block.enabled },
  });

  const mutation = useMutation({
    mutationFn: (data: PromptUpdateInput) => updatePromptBlock(block.block_id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-prompts"] });
      setConfirmOpen(false);
      reset(pendingData ?? undefined);
    },
  });

  const onSubmit = (data: PromptUpdateInput) => {
    setPendingData(data);
    setConfirmOpen(true);
  };

  const handleConfirm = () => {
    if (pendingData) mutation.mutate(pendingData);
  };

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
          {block.trigger_keywords.length > 0 && (
            <div className={styles.keywords}>
              {block.trigger_keywords.map((kw) => (
                <span key={kw} className={styles.chip}>
                  {kw}
                </span>
              ))}
            </div>
          )}

          <label className={styles.enabledLabel}>
            <input type="checkbox" {...register("enabled")} />
            <span>블록 활성화</span>
          </label>

          <textarea className={styles.textarea} rows={10} {...register("content")} />
          {errors.content && (
            <p className={styles.error}>{errors.content.message}</p>
          )}

          {mutation.isError && (
            <p className={styles.error}>
              {mutation.error instanceof Error ? mutation.error.message : "저장 실패"}
            </p>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={() => reset()}
              disabled={!isDirty}
            >
              취소
            </button>
            <button
              type="submit"
              className={styles.saveBtn}
              disabled={!isDirty || mutation.isPending}
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
