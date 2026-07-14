"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchModelParams, fetchPrompts } from "@/features/admin-rag/api/prompts";
import { ModelParamForm } from "@/features/admin-rag/components/ModelParamForm";
import { NewPromptBlockForm } from "@/features/admin-rag/components/NewPromptBlockForm";
import { PromptBlockCard } from "@/features/admin-rag/components/PromptBlockCard";
import styles from "./page.module.css";

export default function PromptManagementPage() {
  const modelQuery = useQuery({
    queryKey: ["admin-rag-model-params"],
    queryFn: fetchModelParams,
    staleTime: 60_000,
  });

  const promptsQuery = useQuery({
    queryKey: ["admin-rag-prompts"],
    queryFn: fetchPrompts,
    staleTime: 60_000,
  });

  const allBlockIds = (promptsQuery.data?.blocks ?? []).map((b) => b.block_id);

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>프롬프트 관리</h1>

      <section className={styles.section}>
        <h2 className={styles.subheading}>모델 파라미터</h2>
        {modelQuery.isLoading && (
          <p className={styles.statusText}>불러오는 중...</p>
        )}
        {modelQuery.isError && (
          <p className={styles.errorText}>모델 파라미터를 불러오지 못했습니다.</p>
        )}
        {modelQuery.data && <ModelParamForm defaults={modelQuery.data} />}
      </section>

      <section className={styles.section}>
        <h2 className={styles.subheading}>프롬프트 블록</h2>
        <NewPromptBlockForm allBlockIds={allBlockIds} />
        {promptsQuery.isLoading && (
          <p className={styles.statusText}>불러오는 중...</p>
        )}
        {promptsQuery.isError && (
          <p className={styles.errorText}>프롬프트 목록을 불러오지 못했습니다.</p>
        )}
        {promptsQuery.data?.blocks.map((block) => (
          <PromptBlockCard key={block.block_id} block={block} allBlockIds={allBlockIds} />
        ))}
      </section>
    </div>
  );
}
