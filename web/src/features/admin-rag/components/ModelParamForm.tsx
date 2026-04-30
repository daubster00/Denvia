"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  modelParamsSchema,
  type ModelParamsInput,
  updateModelParams,
} from "../api/prompts";
import type { ModelParamsResponse } from "../api/prompts";
import styles from "./ModelParamForm.module.css";

interface Props {
  defaults: ModelParamsResponse;
}

export function ModelParamForm({ defaults }: Props) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingData, setPendingData] = useState<ModelParamsInput | null>(null);
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { isDirty, errors },
  } = useForm<ModelParamsInput>({
    resolver: zodResolver(modelParamsSchema),
    defaultValues: defaults,
  });

  const mutation = useMutation({
    mutationFn: updateModelParams,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-model-params"] });
      setConfirmOpen(false);
      reset(pendingData ?? undefined);
    },
  });

  const onSubmit = (data: ModelParamsInput) => {
    setPendingData(data);
    setConfirmOpen(true);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className={styles.form}>
      <div className={styles.field}>
        <label className={styles.label}>k (검색 문서 수, 1~20)</label>
        <input
          type="number"
          min={1}
          max={20}
          step={1}
          className={styles.input}
          {...register("rag_k", { valueAsNumber: true })}
        />
        {errors.rag_k && <p className={styles.error}>{errors.rag_k.message}</p>}
      </div>

      <div className={styles.field}>
        <label className={styles.label}>temperature (0.0~1.0, 0.05 단위)</label>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          className={styles.input}
          {...register("rag_temperature", { valueAsNumber: true })}
        />
        {errors.rag_temperature && (
          <p className={styles.error}>{errors.rag_temperature.message}</p>
        )}
      </div>

      <div className={styles.field}>
        <label className={styles.label}>max_tokens (256~4096)</label>
        <input
          type="number"
          min={256}
          max={4096}
          step={64}
          className={styles.input}
          {...register("max_tokens", { valueAsNumber: true })}
        />
        {errors.max_tokens && (
          <p className={styles.error}>{errors.max_tokens.message}</p>
        )}
      </div>

      {mutation.isError && (
        <p className={styles.error}>
          {mutation.error instanceof Error ? mutation.error.message : "저장 실패"}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          onClick={() => reset()}
          disabled={!isDirty}
          className={styles.cancelBtn}
        >
          취소
        </button>
        <button
          type="submit"
          disabled={!isDirty || mutation.isPending}
          className={styles.saveBtn}
        >
          {mutation.isPending ? "저장 중..." : "저장"}
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="모델 파라미터 저장"
        description="저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?"
        confirmLabel="저장"
        onConfirm={() => pendingData && mutation.mutate(pendingData)}
        onCancel={() => setConfirmOpen(false)}
      />
    </form>
  );
}
