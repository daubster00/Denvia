"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { useQAStore } from "@/stores/qa-store";
import { useAlertStore, type AlertAction } from "@/stores/alert-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 타자기 효과: 글자가 차르륵 흘러나오는 속도(ms/char).
// 너무 빠르면 한꺼번에 보이고, 너무 느리면 답답해진다.
const TYPEWRITER_CHAR_INTERVAL_MS = 28;
// 버퍼가 밀리면 한 틱에 여러 글자를 한꺼번에 흘려보내 따라잡는다.
function typewriterDrainCount(remaining: number): number {
  if (remaining > 200) return 8;
  if (remaining > 100) return 4;
  if (remaining > 40) return 2;
  return 1;
}

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

    // 타자기 버퍼 — SSE 토큰이 들어오는 즉시 store에 찍지 않고 글자 단위 큐로 보낸다.
    // 백엔드는 토큰을 묶어 보낼 때가 있어서 그대로 찍으면 "한꺼번에 팍" 보인다.
    const charBuffer: string[] = [];
    let typewriterTimer: ReturnType<typeof setInterval> | null = null;
    let streamFinished = false;
    let pendingFinalizeId: number | null = null;
    let typewriterDone: () => void = () => {};
    const typewriterPromise = new Promise<void>((resolve) => {
      typewriterDone = resolve;
    });

    const startTypewriter = () => {
      if (typewriterTimer !== null) return;
      typewriterTimer = setInterval(() => {
        const remaining = charBuffer.length;
        if (remaining > 0) {
          const n = typewriterDrainCount(remaining);
          const chunk = charBuffer.splice(0, n).join("");
          addToken(assistantId, chunk);
          return;
        }
        if (streamFinished) {
          if (typewriterTimer !== null) {
            clearInterval(typewriterTimer);
            typewriterTimer = null;
          }
          if (pendingFinalizeId !== null) {
            finalize(assistantId, pendingFinalizeId);
            queryClient.invalidateQueries({ queryKey: ["me", "quota"] });
            pendingFinalizeId = null;
          }
          typewriterDone();
        }
      }, TYPEWRITER_CHAR_INTERVAL_MS);
    };

    const cleanupTypewriter = () => {
      if (typewriterTimer !== null) {
        clearInterval(typewriterTimer);
        typewriterTimer = null;
      }
      charBuffer.length = 0;
      typewriterDone();
    };

    controller.signal.addEventListener("abort", cleanupTypewriter);

    try {
      await fetchEventSource(`${API_BASE}/api/v1/qa/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_text: questionText }),
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(response) {
          // 관리자 차단(question_only) — quota 폴링 간격(60s) 사이에 차단이 들어오면
          // 프론트가 readonly 로 잠그기 전에 사용자가 전송할 수 있다. 그 경우 403 으로
          // 응답하므로 동일한 안내 모달을 띄우고 quota 캐시를 무효화해 즉시 잠근다.
          if (response.status === 403) {
            const body = await response.json().catch(() => ({}));
            const code = body?.code as string | undefined;
            if (code === "QUESTION_BLOCKED") {
              const msg =
                (body?.message as string | undefined) ??
                "관리자에 의해 일시적으로 질문이 제한되었습니다.";
              useAlertStore.getState().show({
                level: "warning",
                title: "이상 활동이 감지되어 질문이 일시 제한되었습니다.",
                description: msg,
                dedupeKey: "question_blocked",
              });
              clearMessages();
              queryClient.invalidateQueries({ queryKey: ["me", "quota"] });
              controller.abort();
              return;
            }
          }
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
          if (ev.event === "token") {
            // 글자 단위로 큐에 쌓고 타자기를 가동한다 (스프레드 = Unicode safe split).
            const delta = data.delta as string;
            for (const ch of [...delta]) charBuffer.push(ch);
            startTypewriter();
          }
          else if (ev.event === "rule_matched") markRuleMatched(assistantId, data.procedure_count);
          else if (ev.event === "reframe") {
            // Story 2.6: snake_case → camelCase 매핑 + 백엔드와 동등한 schema 가드
            if (isValidReframePayload(data)) {
              // reframe은 content를 통째로 교체하므로 버퍼에 남은 글자는 의미 없다.
              charBuffer.length = 0;
              markReframe(assistantId, {
                followUpQuestion: data.follow_up_question.trim().replace(/\s+/g, " "),
                options: data.options.map((o: string) => o.trim()),
              });
            } else {
              console.warn("[useQAStream] invalid reframe payload, ignoring", data);
            }
          }
          else if (ev.event === "done") {
            // 타자기 버퍼가 비워진 다음 finalize 한다.
            streamFinished = true;
            pendingFinalizeId = data.qa_log_id;
            // 이상 질문 패턴 탐지로 throttle 이 새로 적용되었고, 무료 사용자라면
            // 안내 팝업을 띄운다. 유료 사용자는 throttle 적용되어도 팝업 미노출
            // (백엔드 done 이벤트에서 show_popup 을 false 로 내려준다).
            if (data?.show_popup === true) {
              useAlertStore.getState().show({
                level: "warning",
                title: "질문의 속도가 비정상적으로 빨라 이상탐지 되었습니다.",
                description: "답변의 속도를 제한합니다.",
                dedupeKey: "anomaly_throttle_applied",
              });
            }
            startTypewriter();
          }
          else if (ev.event === "error") {
            cleanupTypewriter();
            setError(assistantId, data.message);
          }
        },
        onerror(err) {
          throw err;
        },
      });
      // SSE는 끝났지만 타자기 버퍼가 남아있을 수 있다 — 다 흘러나올 때까지 대기.
      if (typewriterTimer !== null) {
        await typewriterPromise;
      }
    } catch (err) {
      cleanupTypewriter();
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
