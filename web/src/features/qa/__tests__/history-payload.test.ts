/**
 * 서버로 보내는 이전 대화 페이로드 — 2026-11-03 검수 P0-2 · P0-6 · P1-3.
 *
 * 고정하는 규칙:
 *   - 보내는 것은 **서버가 발급한 qa_log_id 뿐**이다 (과거 답변 문자열 금지).
 *   - 화면에 31턴 이상이 쌓여도 요청에는 최신 30개만 실린다 (요청 전체가 422 로
 *     거부되던 결함).
 *   - 중단·오류 답변은 보내지 않는다 (반쪽 답변이 신뢰된 맥락이 되면 안 된다).
 */
import { describe, expect, it } from "vitest";
import {
  MAX_HISTORY_TURN_IDS,
  toHistoryTurnIds,
} from "@/features/qa/hooks/useQAStream";
import type { QAMessage } from "@/stores/qa-store";

function turn(
  index: number,
  opts: {
    status?: QAMessage["status"];
    qaLogId?: number;
    answer?: string;
    question?: string;
  } = {},
): QAMessage[] {
  const status = opts.status ?? "complete";
  return [
    {
      id: `u${index}`,
      role: "user",
      content: opts.question ?? `질문${index}`,
      status: "complete",
      timestamp: "2026-01-01T00:00:00.000Z",
    },
    {
      id: `a${index}`,
      role: "assistant",
      content: opts.answer ?? `답변${index}`,
      status,
      qaLogId: opts.qaLogId,
      timestamp: "2026-01-01T00:00:00.000Z",
    },
  ];
}

describe("toHistoryTurnIds", () => {
  it("정상 완료된 턴의 qa_log_id 만 오래된 것 → 최신 순으로 보낸다", () => {
    const messages = [
      ...turn(1, { qaLogId: 101 }),
      ...turn(2, { qaLogId: 102 }),
    ];
    expect(toHistoryTurnIds(messages)).toEqual([101, 102]);
  });

  it("qa_log_id 가 없는 턴은 보내지 않는다 (서버가 확인할 수 없는 턴)", () => {
    const messages = [...turn(1, {}), ...turn(2, { qaLogId: 102 })];
    expect(toHistoryTurnIds(messages)).toEqual([102]);
  });

  it("중단·오류 답변은 맥락으로 보내지 않는다 (검수 P1-3)", () => {
    const messages = [
      ...turn(1, { status: "error", qaLogId: 101, answer: "답변 일부" }),
      ...turn(2, { status: "pending", qaLogId: 102, answer: "답변 일부" }),
      ...turn(3, { qaLogId: 103 }),
    ];
    expect(toHistoryTurnIds(messages)).toEqual([103]);
  });

  it("31턴이 화면에 있어도 요청에는 최신 30개만 실린다 (검수 P0-6)", () => {
    const messages = Array.from({ length: 31 }, (_, i) =>
      turn(i + 1, { qaLogId: 1000 + i }),
    ).flat();

    const ids = toHistoryTurnIds(messages);

    expect(ids).toHaveLength(MAX_HISTORY_TURN_IDS);
    expect(ids[0]).toBe(1001); // 가장 오래된 1턴(1000)은 빠진다
    expect(ids[ids.length - 1]).toBe(1030); // 최신 턴은 반드시 포함
  });

  it("32번째 질문도 최신 30개로 정상 처리된다", () => {
    const messages = Array.from({ length: 40 }, (_, i) =>
      turn(i + 1, { qaLogId: 2000 + i }),
    ).flat();
    const ids = toHistoryTurnIds(messages);
    expect(ids).toHaveLength(MAX_HISTORY_TURN_IDS);
    expect(ids[ids.length - 1]).toBe(2039);
  });

  it("아주 긴 과거 답변이 있어도 id 만 보내므로 요청 크기와 무관하다", () => {
    const messages = turn(1, { qaLogId: 101, answer: "가".repeat(20000) });
    expect(toHistoryTurnIds(messages)).toEqual([101]);
  });

  it("질문이 비어 있으면 보내지 않는다", () => {
    const messages = turn(1, { qaLogId: 101, question: "   " });
    expect(toHistoryTurnIds(messages)).toEqual([]);
  });

  it("대화가 없으면 빈 배열", () => {
    expect(toHistoryTurnIds([])).toEqual([]);
  });

  it("상한 값이 서버 스키마와 같은 30 이다", () => {
    expect(MAX_HISTORY_TURN_IDS).toBe(30);
  });
});
