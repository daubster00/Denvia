"use client";

import { useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQAStore } from "@/stores/qa-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useQAStream() {
  const replaceMessages = useQAStore((s) => s.replaceMessages);
  const addToken = useQAStore((s) => s.addToken);
  const markRuleMatched = useQAStore((s) => s.markRuleMatched);
  const finalize = useQAStore((s) => s.finalize);
  const setError = useQAStore((s) => s.setError);
  const abortRef = useRef<AbortController | null>(null);

  async function submit(questionText: string) {
    // AC-7: 이전 스트림 자동 취소
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    const now = new Date().toISOString();
    // 클라이언트 기획서 §3: 새 질문 시 이전 대화 모두 삭제하고 신규 1질의응답만 표시 (PRD SSOT 편차)
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
        onmessage(ev) {
          const data = JSON.parse(ev.data);
          if (ev.event === "token") addToken(assistantId, data.delta);
          else if (ev.event === "rule_matched") markRuleMatched(assistantId, data.procedure_count);
          else if (ev.event === "done") finalize(assistantId, data.qa_log_id);
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
