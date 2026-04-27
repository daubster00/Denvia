"use client";

import { useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { useQAStore } from "@/stores/qa-store";
import { useQuotaStore } from "@/stores/quota-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useQAStream() {
  const replaceMessages = useQAStore((s) => s.replaceMessages);
  const clearMessages = useQAStore((s) => s.clearMessages);
  const addToken = useQAStore((s) => s.addToken);
  const markRuleMatched = useQAStore((s) => s.markRuleMatched);
  const finalize = useQAStore((s) => s.finalize);
  const setError = useQAStore((s) => s.setError);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  async function submit(questionText: string) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    const now = new Date().toISOString();
    // 클라이언트 기획서 §3: 새 질문 시 이전 대화 모두 삭제하고 신규 1질의응답만 표시
    replaceMessages([
      { id: userId, role: "user", content: questionText, status: "complete", timestamp: now },
      { id: assistantId, role: "assistant", content: "", status: "pending", timestamp: now },
    ]);

    try {
      await fetchEventSource(`${API_BASE}/api/v1/qa/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_text: questionText }),
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(response) {
          // Story 2.3: SSE 시작 전 429 분기 (일반 JSON 응답 — SSE 아님)
          if (response.status === 429) {
            const body = await response.json().catch(() => ({}));
            const code = body?.code as string | undefined;
            const details = body?.details ?? {};
            if (
              code === "QUOTA_EXCEEDED" ||
              code === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT"
            ) {
              useQuotaStore.getState().lock({
                reason: code as "QUOTA_EXCEEDED" | "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT",
                dailyLimit: details.daily_limit ?? 10,
                usedToday: details.used_today ?? details.daily_limit ?? 0,
                resetAt: details.reset_at ?? null,
                showUpgradePrompt: details.show_upgrade_prompt ?? false,
                showSubscribeButton: details.show_subscribe_button ?? true,
              });
              // 1문 1답 정책: 한도 차단 시 이전 메시지 제거
              clearMessages();
              controller.abort();
              return;
            }
          }
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
        },
        onmessage(ev) {
          const data = JSON.parse(ev.data);
          if (ev.event === "token") addToken(assistantId, data.delta);
          else if (ev.event === "rule_matched") markRuleMatched(assistantId, data.procedure_count);
          else if (ev.event === "done") {
            finalize(assistantId, data.qa_log_id);
            // Story 2.3: done 이벤트 시 quota 카운터 즉시 갱신 (AC-8)
            queryClient.invalidateQueries({ queryKey: ["me", "quota"] });
          }
          else if (ev.event === "error") setError(assistantId, data.message);
        },
        onerror(err) {
          throw err;
        },
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(assistantId, "답변 생성에 실패했습니다. 다시 시도해주세요.");
      }
    }
  }

  return { submit };
}
