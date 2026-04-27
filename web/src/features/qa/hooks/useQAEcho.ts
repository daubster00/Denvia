"use client";

import { useState } from "react";
import { useQAStore } from "@/stores/qa-store";

export function useQAEcho() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const addMessage = useQAStore((s) => s.addMessage);
  const updateMessage = useQAStore((s) => s.updateMessage);

  async function submit(questionText: string) {
    if (!questionText.trim()) return;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    const now = new Date().toISOString();

    addMessage({ id: userId, role: "user", content: questionText, status: "complete", timestamp: now });
    addMessage({ id: assistantId, role: "assistant", content: "", status: "pending", timestamp: now });

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/v1/qa/echo", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_text: questionText }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      updateMessage(assistantId, {
        content: data.answer_text,
        qaLogId: data.qa_log_id,
        status: "complete",
      });
    } catch (err) {
      updateMessage(assistantId, { content: "오류가 발생했습니다. 다시 시도해주세요.", status: "error" });
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }

  return { submit, loading, error };
}
