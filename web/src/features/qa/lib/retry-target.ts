import { historyTurnIdsBefore, type QAMessage } from "@/stores/qa-store";

/**
 * 오류 답변의 "다시 시도" 가 **어떤 질문**을 다시 보내야 하는지 찾는다 (검수 P1-6).
 *
 * 예전에는 어떤 답변의 버튼을 눌러도 `lastUserTextRef`(가장 최근 질문)를 다시 보냈다.
 * 대화가 쌓이는 지금은 위쪽 오류 답변을 눌렀을 때 엉뚱한 질문이 다시 전송된다.
 * 그 답변 **바로 앞의 사용자 질문**이 정답이다.
 *
 * 찾지 못하면 null — 호출부는 아무것도 보내지 않는다(엉뚱한 질문을 보내는 것보다 낫다).
 */
export function resolveRetryQuestion(
  messages: QAMessage[],
  assistantMessageId: string,
): string | null {
  const idx = messages.findIndex((m) => m.id === assistantMessageId);
  if (idx <= 0) return null;
  const prev = messages[idx - 1];
  if (prev.role !== "user") return null;
  const question = prev.content.trim();
  return question ? question : null;
}

export interface RetryTarget {
  /** 다시 보낼 질문 본문. */
  question: string;
  /** 그 질문을 **최초로 보낼 때** 쓴 이전 대화 턴 id 목록. */
  historyTurnIds: number[];
  /** 스냅샷을 그대로 썼는가 (false = 구버전 메시지라 다시 계산했다). */
  fromSnapshot: boolean;
}

/**
 * 재시도에 필요한 것 전부 — 질문 + **최초 요청 당시의 맥락** (재수정 P1-2).
 *
 * ## 왜 "지금 대화" 를 다시 계산하면 안 되는가
 *
 * A 질문이 오류로 끝나고, 사용자가 B 를 물어 정상 답변을 받은 뒤 A 의 "다시 시도" 를
 * 누른 경우를 보자. 지금 화면의 완료 턴을 전부 계산하면 **B 의 로그 id** 가 A 의
 * 맥락으로 들어간다. 시간상 A 보다 뒤에 일어난 대화가 A 의 앞 맥락이 되는 셈이다.
 *
 * 결과는 두 가지로 터진다.
 *
 *   1. 질문 재작성(연관성 판단)이 B 의 주제를 끌어와 A 의 검색 질의를 엉뚱하게 완성한다.
 *      치과 청구에서 다른 항목의 기준이 섞이는 것이 가장 위험한 실패다.
 *   2. 서버가 만드는 맥락 지문(`history_context_key`)이 최초 요청과 달라져,
 *      전송 못 한 저장 답변의 재생이 어긋난다(검수 P0-1 게이팅).
 *
 * 그래서 답변 메시지에 최초 요청 당시의 맥락을 스냅샷해 두고(`QAMessage.historyTurnIds`)
 * 재시도는 그 값을 쓴다.
 *
 * 스냅샷이 없는 경우(배포 전 열려 있던 탭에 남은 구버전 메시지)는
 * `historyTurnIdsBefore` 로 **재시도 대상 질문 이전의 완료 턴만** 계산한다 —
 * 전체를 다시 계산하는 것보다 최초 맥락에 훨씬 가깝다.
 */
export function resolveRetryTarget(
  messages: QAMessage[],
  assistantMessageId: string,
): RetryTarget | null {
  const question = resolveRetryQuestion(messages, assistantMessageId);
  if (!question) return null;

  const target = messages.find((m) => m.id === assistantMessageId);
  const snapshot = target?.historyTurnIds;
  if (Array.isArray(snapshot)) {
    return { question, historyTurnIds: [...snapshot], fromSnapshot: true };
  }
  return {
    question,
    historyTurnIds: historyTurnIdsBefore(messages, assistantMessageId),
    fromSnapshot: false,
  };
}
