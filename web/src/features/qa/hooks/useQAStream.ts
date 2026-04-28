"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { useQAStore } from "@/stores/qa-store";
import { useAlertStore, type AlertAction } from "@/stores/alert-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Story 2.6: 백엔드 ReframePayload 검증과 동등한 schema 가드
function isValidReframePayload(
  raw: unknown,
): raw is { follow_up_question: string; options: string[] } {
  if (typeof raw !== "object" || raw === null) return false;
  const candidate = raw as { follow_up_question?: unknown; options?: unknown };
  if (typeof candidate.follow_up_question !== "string") return false;
  if (candidate.follow_up_question.trim().length === 0) return false;
  if (!Array.isArray(candidate.options)) return false;
  if (candidate.options.length < 3 || candidate.options.length > 4) return false;
  for (const opt of candidate.options) {
    if (typeof opt !== "string") return false;
    if (opt.includes("\n") || opt.includes("\r")) return false;
    const trimmed = opt.trim();
    if (trimmed.length < 1 || trimmed.length > 120) return false;
  }
  return true;
}

export function useQAStream() {
  const router = useRouter();
  const replaceMessages = useQAStore((s) => s.replaceMessages);
  const clearMessages = useQAStore((s) => s.clearMessages);
  const addToken = useQAStore((s) => s.addToken);
  const markRuleMatched = useQAStore((s) => s.markRuleMatched);
  const finalize = useQAStore((s) => s.finalize);
  const setError = useQAStore((s) => s.setError);
  const markReframe = useQAStore((s) => s.markReframe);
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
            const details = (body?.details ?? body) as Record<string, unknown>;
            if (
              code === "QUOTA_EXCEEDED" ||
              code === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT"
            ) {
              const isInternal = code === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";
              const dailyLimit = (details.daily_limit as number | undefined) ?? 10;
              const showSubscribe =
                (details.show_subscribe_button as boolean | undefined) ?? true;

              const actions: AlertAction[] = isInternal
                ? [{ label: "확인", variant: "normal" }]
                : [
                    { label: "내일 다시", variant: "assistive" },
                    ...(showSubscribe
                      ? [
                          {
                            label: "Pro로 계속",
                            variant: "normal" as const,
                            onClick: () => router.push("/subscribe"),
                          },
                        ]
                      : []),
                  ];

              useAlertStore.getState().show({
                level: "warning",
                title: isInternal
                  ? "일시적 시스템 보호 제한에 도달했습니다."
                  : `오늘의 ${dailyLimit}회를 모두 사용했어요.`,
                description: isInternal
                  ? "고객문의로 연락주세요."
                  : "내일 다시 오시거나, Pro로 계속 진료에 활용해보세요.",
                actions,
                dedupeKey: code,
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
          else if (ev.event === "reframe") {
            // Story 2.6: snake_case → camelCase 매핑 + 백엔드와 동등한 schema 가드
            if (isValidReframePayload(data)) {
              markReframe(assistantId, {
                followUpQuestion: data.follow_up_question.trim().replace(/\s+/g, " "),
                options: data.options.map((o: string) => o.trim()),
              });
            } else {
              console.warn("[useQAStream] invalid reframe payload, ignoring", data);
            }
          }
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

  function abort() {
    abortRef.current?.abort();
    abortRef.current = null;
  }

  return { submit, abort };
}
