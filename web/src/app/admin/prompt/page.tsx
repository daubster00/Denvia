"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchModelParams,
  fetchPromptModelRoutes,
  fetchPrompts,
} from "@/features/admin-rag/api/prompts";
import { ModelParamForm } from "@/features/admin-rag/components/ModelParamForm";
import { NewPromptBlockForm } from "@/features/admin-rag/components/NewPromptBlockForm";
import { PromptBlockCard } from "@/features/admin-rag/components/PromptBlockCard";
import { PromptModelRouteForm } from "@/features/admin-rag/components/PromptModelRouteForm";
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

  // 블록 카드에 "이 블록에 별도 모델이 걸려 있다" 배지를 띄우기 위해 지정 목록도 읽는다.
  // PromptModelRouteForm 과 같은 queryKey 라 캐시를 공유한다(중복 요청 없음).
  const routesQuery = useQuery({
    queryKey: ["admin-rag-prompt-model-routes"],
    queryFn: fetchPromptModelRoutes,
    staleTime: 60_000,
  });

  const allBlockIds = (promptsQuery.data?.blocks ?? []).map((b) => b.block_id);

  // block_id → 적용 모델. 꺼진 지정은 배지를 달지 않는다(실제로 안 쓰이므로).
  const routedModelByBlock = new Map<string, string>(
    (routesQuery.data?.routes ?? [])
      .filter((r) => r.enabled)
      .map((r) => [r.block_id, r.model]),
  );

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
        <h2 className={styles.subheading}>특정 프롬프트 모델 설정</h2>
        <PromptModelRouteForm blockIds={allBlockIds} />
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
          <PromptBlockCard
            key={block.block_id}
            block={block}
            allBlockIds={allBlockIds}
            routedModel={routedModelByBlock.get(block.block_id) ?? null}
          />
        ))}
      </section>
    </div>
  );
}
