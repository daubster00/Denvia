"use client";
import { useEffect, useState } from "react";
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
  const [helpOpen, setHelpOpen] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!helpOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setHelpOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [helpOpen]);

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
        <div className={styles.labelRow}>
          <label className={styles.label}>max_tokens (256~4096)</label>
          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            className={styles.helpBtn}
            aria-label="max_tokens 안내 보기"
            data-no-admin-height
          >
            ?
          </button>
        </div>
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

      <div className={styles.field}>
        <label className={styles.label}>
          입력 글자수 제한 (사용자 질문, 100~5000)
        </label>
        <input
          type="number"
          min={100}
          max={5000}
          step={100}
          className={styles.input}
          {...register("max_question_chars", { valueAsNumber: true })}
        />
        {errors.max_question_chars && (
          <p className={styles.error}>{errors.max_question_chars.message}</p>
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

      {helpOpen && (
        <div
          role="presentation"
          className={styles.helpOverlay}
          onClick={(e) => {
            if (e.target === e.currentTarget) setHelpOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="max-tokens-help-title"
            className={styles.helpDialog}
          >
            <div className={styles.helpHeader}>
              <h2 id="max-tokens-help-title" className={styles.helpTitle}>
                max_tokens 가이드
              </h2>
              <button
                type="button"
                onClick={() => setHelpOpen(false)}
                className={styles.helpClose}
                aria-label="닫기"
              >
                ×
              </button>
            </div>

            <p className={styles.helpIntro}>
              한 번의 답변에 들어갈 <strong>최대 분량</strong>을 정합니다.
              한도에 닿으면 답변이 문장 중간에서도 잘리므로 여유 있게 설정하세요.
            </p>

            <table className={styles.helpTable}>
              <thead>
                <tr>
                  <th>구간</th>
                  <th>토큰</th>
                  <th>한글 분량(대략)</th>
                  <th>체감 길이</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>최소</td>
                  <td>1024</td>
                  <td>약 600~700자</td>
                  <td>짧은 단락 2~3개</td>
                </tr>
                <tr>
                  <td>중간</td>
                  <td>2048</td>
                  <td>약 1,200~1,400자</td>
                  <td>A4 반 페이지</td>
                </tr>
                <tr>
                  <td>중상</td>
                  <td>3072</td>
                  <td>약 1,800~2,100자</td>
                  <td>A4 한 페이지</td>
                </tr>
                <tr>
                  <td>최대</td>
                  <td>4096</td>
                  <td>약 2,400~2,800자</td>
                  <td>A4 1.2 페이지</td>
                </tr>
              </tbody>
            </table>

            <p className={styles.helpNote}>
              ※ 한글 1자 ≈ 1.3~1.7 토큰. 전문용어·숫자·표 기호가 많을수록
              토큰 소비가 늘어 실제 분량은 더 짧아질 수 있습니다.
              값이 클수록 응답 시간과 API 비용도 함께 증가합니다.
            </p>
          </div>
        </div>
      )}
    </form>
  );
}
