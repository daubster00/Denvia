"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  fetchChatModelConfig,
  formatModelPrice,
  type ChatModelInfo,
} from "@/features/admin-dashboard/api/chatModel";
import {
  fetchPromptModelRoutes,
  updatePromptModelRoutes,
  type PromptModelRouteItem,
  type PromptModelRoutes,
} from "../api/prompts";
import styles from "./PromptModelRouteForm.module.css";

interface Props {
  /** 프롬프트 블록 목록 — BASE 는 호출 측에서 넘겨도 여기서 제외한다. */
  blockIds: string[];
}

const sameRoutes = (a: PromptModelRouteItem[], b: PromptModelRouteItem[]) =>
  JSON.stringify(a) === JSON.stringify(b);

/**
 * 특정 프롬프트 모델 설정 — 프롬프트 블록별로 다른 API 모델을 지정한다(복수 가능).
 *
 * 지정한 블록이 사용자 질문에 의해 **실제로 최종 프롬프트에 주입된 경우에만** 그 모델이
 * 쓰이고, 그 외 질문(키워드만 포함 / 블록 꺼짐 / 상호배제로 탈락 / 일반 질문)은 기본
 * 모델을 그대로 쓴다. 질문 복잡도 분석이나 별도 분류 호출은 하지 않는다.
 *
 * 목록 순서 = 우선순위. 한 질문에 지정 블록이 둘 이상 주입되면 위에 있는 지정이 이긴다.
 * 편집은 로컬에서 하고(추가·변경·삭제·순서), [저장]을 눌러야 서버에 반영된다.
 */
export function PromptModelRouteForm({ blockIds }: Props) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<PromptModelRouteItem[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  // 추가 폼 — 열려 있을 때만 선택값을 들고 있는다.
  const [adding, setAdding] = useState(false);
  const [newBlockId, setNewBlockId] = useState("");
  const [newModel, setNewModel] = useState("");

  const routesQuery = useQuery({
    queryKey: ["admin-rag-prompt-model-routes"],
    queryFn: fetchPromptModelRoutes,
    staleTime: 60_000,
  });

  // 현재 기본 모델(runtime:chat_model) — "다른 질문에는 무엇이 쓰이는지" 표시 전용.
  // 조회 실패해도 이 폼의 저장 기능에는 영향이 없다.
  const baseModelQuery = useQuery({
    queryKey: ["admin-chat-model-config"],
    queryFn: fetchChatModelConfig,
    staleTime: 60_000,
  });

  useEffect(() => {
    const data = routesQuery.data;
    if (!data) return;
    setDraft(data.routes.map((r) => ({ ...r })));
  }, [routesQuery.data]);

  // BASE 는 모든 질문에 항상 포함되므로 대상이 될 수 없다 → 목록에서 제외.
  const selectableBlocks = useMemo(
    () => blockIds.filter((id) => id !== "BASE"),
    [blockIds],
  );

  const mutation = useMutation({
    mutationFn: updatePromptModelRoutes,
    onSuccess: (updated: PromptModelRoutes) => {
      queryClient.setQueryData(["admin-rag-prompt-model-routes"], updated);
      setConfirmOpen(false);
      setAdding(false);
      const on = updated.routes.filter((r) => r.enabled).length;
      setSavedMessage(
        updated.routes.length === 0
          ? "저장했습니다. 지정이 없으므로 모든 질문이 기본 모델을 사용합니다."
          : `저장했습니다. 지정 ${updated.routes.length}개(적용중 ${on}개)가 다음 질문부터 반영됩니다.`,
      );
    },
  });

  if (routesQuery.isLoading) {
    return <p className={styles.description}>불러오는 중...</p>;
  }
  if (routesQuery.isError || !routesQuery.data) {
    return (
      <p className={styles.error}>특정 프롬프트 모델 설정을 불러오지 못했습니다.</p>
    );
  }

  const server = routesQuery.data;
  const baseModel =
    baseModelQuery.data?.chat_model ?? server.default_model ?? "기본 모델";
  const dirty = !sameRoutes(draft, server.routes);
  // 이미 지정된 블록은 추가 목록에서 뺀다 — 프롬프트 1개당 모델 1개.
  const addableBlocks = selectableBlocks.filter(
    (id) => !draft.some((r) => r.block_id === id),
  );

  const patch = (idx: number, next: Partial<PromptModelRouteItem>) => {
    setSavedMessage(null);
    setDraft((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, ...next } : r)),
    );
  };

  const move = (idx: number, delta: number) => {
    const target = idx + delta;
    if (target < 0 || target >= draft.length) return;
    setSavedMessage(null);
    setDraft((prev) => {
      const next = [...prev];
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const remove = (idx: number) => {
    setSavedMessage(null);
    setDraft((prev) => prev.filter((_, i) => i !== idx));
  };

  const addRoute = () => {
    if (!newBlockId || !newModel) return;
    setSavedMessage(null);
    setDraft((prev) => [
      ...prev,
      { block_id: newBlockId, model: newModel, enabled: true },
    ]);
    setNewBlockId("");
    setNewModel("");
    setAdding(false);
  };

  // 추가 폼에서 고른 모델의 가격·설명 — "이걸 고르면 얼마" 를 고르는 순간 보여준다.
  const newModelSpec: ChatModelInfo | undefined = server.models.find(
    (m) => m.model_id === newModel,
  );

  const errorText = mutation.isError
    ? mutation.error instanceof Error
      ? mutation.error.message
      : "저장 실패"
    : null;

  return (
    <div className={styles.panel}>
      <p className={styles.description}>
        지정한 프롬프트가 실제로 작동하는 질문에만 그 모델이 사용됩니다. 다른 질문에는
        기본 모델이 사용됩니다.
      </p>
      <p className={styles.footnote}>
        ※ 지정이 없는 질문 →{" "}
        <span className={styles.summaryStrong}>{baseModel}</span> (기본 모델)
      </p>

      {draft.length > 0 ? (
        <>
          <p className={styles.priorityNote}>
            한 질문에 여러 지정이 동시에 작동하면 <strong>위에 있는 지정</strong>이
            우선 적용됩니다. ↑↓ 로 순서를 바꾸세요.
          </p>

          <ul className={styles.list}>
            {draft.map((route, idx) => {
              const missing = !selectableBlocks.includes(route.block_id);
              return (
                <li
                  key={`${route.block_id}-${idx}`}
                  className={
                    route.enabled ? styles.row : `${styles.row} ${styles.rowOff}`
                  }
                >
                  <span className={styles.rank}>{idx + 1}</span>

                  <div className={styles.rowMain}>
                    <span className={styles.rowBlock}>{route.block_id}</span>
                    <span className={styles.rowArrow}>→</span>
                    <select
                      className={styles.rowSelect}
                      aria-label={`${route.block_id} 적용 모델`}
                      value={route.model}
                      onChange={(e) => patch(idx, { model: e.target.value })}
                    >
                      {server.models.map((m) => (
                        <option key={m.model_id} value={m.model_id}>
                          {m.model_id} (출력 ${m.output_usd_per_mtok.toFixed(2)})
                        </option>
                      ))}
                    </select>
                    {missing && (
                      <span className={styles.missingBadge}>삭제된 프롬프트</span>
                    )}
                  </div>

                  <div className={styles.rowSide}>
                    <label className={styles.onOff}>
                      <input
                        type="checkbox"
                        className={styles.checkbox}
                        checked={route.enabled}
                        onChange={(e) => patch(idx, { enabled: e.target.checked })}
                      />
                      {route.enabled ? "적용중" : "꺼짐"}
                    </label>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      aria-label="위로"
                      disabled={idx === 0}
                      onClick={() => move(idx, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      aria-label="아래로"
                      disabled={idx === draft.length - 1}
                      onClick={() => move(idx, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className={styles.linkDangerBtn}
                      onClick={() => remove(idx)}
                    >
                      삭제
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p className={styles.emptyTitle}>
          지정된 프롬프트가 없습니다. 모든 질문이 기본 모델(
          <span className={styles.summaryStrong}>{baseModel}</span>)을 사용합니다.
        </p>
      )}

      {adding ? (
        <div className={styles.addBox}>
          <div className={styles.addFields}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="new-route-block">
                대상 프롬프트
              </label>
              <select
                id="new-route-block"
                className={styles.select}
                value={newBlockId}
                onChange={(e) => setNewBlockId(e.target.value)}
              >
                <option value="">선택하세요</option>
                {addableBlocks.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="new-route-model">
                적용 모델
              </label>
              <select
                id="new-route-model"
                className={styles.select}
                value={newModel}
                onChange={(e) => setNewModel(e.target.value)}
              >
                <option value="">선택하세요</option>
                {server.models.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.label} — 출력 ${m.output_usd_per_mtok.toFixed(2)}/100만 토큰
                  </option>
                ))}
              </select>
            </div>
          </div>
          {newModelSpec && (
            <p className={styles.priceNote}>
              {newModelSpec.label} · {formatModelPrice(newModelSpec)} · {newModelSpec.note}
            </p>
          )}
          {addableBlocks.length === 0 && (
            <p className={styles.footnote}>
              추가할 수 있는 프롬프트가 없습니다. 모든 프롬프트에 이미 모델이 지정돼
              있습니다.
            </p>
          )}
          <div className={styles.addActions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={() => {
                setAdding(false);
                setNewBlockId("");
                setNewModel("");
              }}
            >
              취소
            </button>
            <button
              type="button"
              className={styles.saveBtn}
              disabled={!newBlockId || !newModel}
              onClick={addRoute}
            >
              목록에 추가
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={styles.addBtn}
          disabled={addableBlocks.length === 0}
          onClick={() => {
            setSavedMessage(null);
            setAdding(true);
          }}
        >
          + 지정 추가
        </button>
      )}

      {dirty && (
        <p className={styles.dirtyNote}>
          변경사항이 아직 저장되지 않았습니다. [저장]을 눌러야 챗봇에 반영됩니다.
        </p>
      )}
      {errorText && <p className={styles.error}>{errorText}</p>}
      {savedMessage && <p className={styles.saved}>{savedMessage}</p>}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.cancelBtn}
          disabled={!dirty || mutation.isPending}
          onClick={() => {
            setDraft(server.routes.map((r) => ({ ...r })));
            setAdding(false);
            setSavedMessage(null);
          }}
        >
          취소
        </button>
        <button
          type="button"
          className={styles.saveBtn}
          disabled={!dirty || mutation.isPending}
          onClick={() => {
            setSavedMessage(null);
            setConfirmOpen(true);
          }}
        >
          {mutation.isPending ? "저장 중..." : "저장"}
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="특정 프롬프트 모델 설정 저장"
        description={
          draft.length === 0
            ? "지정을 모두 비웁니다. 모든 질문이 기본 모델을 사용합니다."
            : `지정 ${draft.length}개를 저장합니다(적용중 ${draft.filter((r) => r.enabled).length}개). 저장 즉시 다음 질문부터 반영됩니다.`
        }
        confirmLabel="저장"
        isSubmitting={mutation.isPending}
        onConfirm={() => mutation.mutate({ routes: draft })}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
