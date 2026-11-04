/**
 * 과거 오류 답변 재시도의 **맥락 복원** — 2026-11-03 재수정 P1-2.
 *
 * ## 무엇이 틀렸었나
 *
 * A 질문이 오류로 끝나고, 사용자가 B 를 물어 정상 답변을 받은 뒤 A 의 "다시 시도" 를
 * 누르면, 재시도 요청이 **지금 화면의 완료 턴 전부**를 맥락으로 계산해 보냈다.
 * 그 결과 B 의 로그 id 가 A 의 맥락으로 들어간다 — 시간상 A 보다 뒤에 일어난 대화가
 * A 의 앞 맥락이 되는 셈이다.
 *
 * 터지는 지점이 둘이다.
 *   1. 질문 재작성(연관성 판단)이 B 의 주제를 끌어와 A 의 검색 질의를 엉뚱하게 완성한다.
 *      치과 청구에서 서로 다른 항목의 기준이 섞이는 것이 가장 위험한 실패다.
 *   2. 서버가 만드는 맥락 지문(`history_context_key`)이 최초 요청과 달라져,
 *      전송 못 한 저장 답변의 재생(검수 P0-1 게이팅)이 어긋난다.
 *
 * ## 고정하는 것
 *   - 답변 메시지에 박아 둔 스냅샷(`historyTurnIds`)을 그대로 쓴다.
 *   - 스냅샷이 없는 구버전 메시지는 **재시도 대상 질문 이전의 완료 턴만** 계산한다.
 */
import { describe, expect, it } from "vitest";

import { resolveRetryTarget } from "@/features/qa/lib/retry-target";
import { historyTurnIdsBefore, type QAMessage } from "@/stores/qa-store";

function msg(partial: Partial<QAMessage> & Pick<QAMessage, "id" | "role">): QAMessage {
  return {
    content: "",
    status: "complete",
    timestamp: "2026-01-01T00:00:00.000Z",
    ...partial,
  } as QAMessage;
}

/**
 * 시나리오: 맥락 0턴에서 A 를 물었다가 오류 → B 를 물어 정상 완료(로그 202)
 *           → 다시 A 의 "다시 시도".
 */
const A_ERROR_THEN_B_OK: QAMessage[] = [
  msg({ id: "uA", role: "user", content: "스케일링 산정 기준" }),
  msg({
    id: "aA",
    role: "assistant",
    content: "",
    status: "error",
    historyTurnIds: [],           // A 를 처음 물었을 때 맥락은 비어 있었다
  }),
  msg({ id: "uB", role: "user", content: "임플란트 보험 적용 조건" }),
  msg({
    id: "aB",
    role: "assistant",
    content: "임플란트는 ...",
    status: "complete",
    qaLogId: 202,
    historyTurnIds: [],
  }),
];

describe("A 오류 → B 정상 완료 → A 재시도 (재수정 P1-2)", () => {
  it("B 의 로그 id 가 전송되지 않는다", () => {
    const target = resolveRetryTarget(A_ERROR_THEN_B_OK, "aA");

    expect(target).not.toBeNull();
    expect(target!.question).toBe("스케일링 산정 기준");
    expect(target!.historyTurnIds).not.toContain(202);
    expect(target!.historyTurnIds).toEqual([]);
  });

  it("최초 A 요청의 맥락과 재시도 맥락이 같다", () => {
    const original = A_ERROR_THEN_B_OK.find((m) => m.id === "aA")!.historyTurnIds!;
    const target = resolveRetryTarget(A_ERROR_THEN_B_OK, "aA")!;

    expect(target.historyTurnIds).toEqual(original);
    expect(target.fromSnapshot).toBe(true);
  });

  it("맥락이 있던 질문도 그 당시 맥락 그대로 복원한다", () => {
    const conversation: QAMessage[] = [
      msg({ id: "u0", role: "user", content: "스케일링 산정 기준" }),
      msg({
        id: "a0",
        role: "assistant",
        content: "3분의1악당 1회",
        status: "complete",
        qaLogId: 101,
        historyTurnIds: [],
      }),
      msg({ id: "uA", role: "user", content: "그럼 치주질환 있으면?" }),
      msg({
        id: "aA",
        role: "assistant",
        content: "",
        status: "error",
        historyTurnIds: [101],     // A 요청 당시 맥락
      }),
      msg({ id: "uB", role: "user", content: "임플란트 조건" }),
      msg({
        id: "aB",
        role: "assistant",
        content: "임플란트는 ...",
        status: "complete",
        qaLogId: 202,
        historyTurnIds: [101],
      }),
    ];

    const target = resolveRetryTarget(conversation, "aA")!;

    expect(target.historyTurnIds).toEqual([101]);
    expect(target.historyTurnIds).not.toContain(202);
  });

  it("마지막 턴의 재시도도 스냅샷을 쓴다", () => {
    const conversation: QAMessage[] = [
      ...A_ERROR_THEN_B_OK,
      msg({ id: "uC", role: "user", content: "틀니 본인부담금" }),
      msg({
        id: "aC",
        role: "assistant",
        content: "",
        status: "error",
        historyTurnIds: [202],
      }),
    ];

    const target = resolveRetryTarget(conversation, "aC")!;
    expect(target.question).toBe("틀니 본인부담금");
    expect(target.historyTurnIds).toEqual([202]);
  });
});

describe("스냅샷이 없는 구버전 메시지 폴백 (재수정 P1-2)", () => {
  it("재시도 대상 질문 **이전**의 완료 턴만 계산한다", () => {
    const legacy: QAMessage[] = [
      msg({ id: "u0", role: "user", content: "스케일링 산정 기준" }),
      msg({
        id: "a0",
        role: "assistant",
        content: "3분의1악당 1회",
        status: "complete",
        qaLogId: 101,
      }),
      msg({ id: "uA", role: "user", content: "그럼 치주질환 있으면?" }),
      msg({ id: "aA", role: "assistant", content: "", status: "error" }),
      msg({ id: "uB", role: "user", content: "임플란트 조건" }),
      msg({
        id: "aB",
        role: "assistant",
        content: "임플란트는 ...",
        status: "complete",
        qaLogId: 202,
      }),
    ];

    const target = resolveRetryTarget(legacy, "aA")!;

    expect(target.fromSnapshot).toBe(false);
    // A 이전의 완료 턴(101)만. 뒤에 일어난 B(202)는 빠진다.
    expect(target.historyTurnIds).toEqual([101]);
    expect(target.historyTurnIds).not.toContain(202);
  });

  it("맥락이 없던 첫 질문의 재시도는 빈 목록", () => {
    const legacy: QAMessage[] = [
      msg({ id: "uA", role: "user", content: "스케일링 산정 기준" }),
      msg({ id: "aA", role: "assistant", content: "", status: "error" }),
      msg({ id: "uB", role: "user", content: "임플란트 조건" }),
      msg({
        id: "aB",
        role: "assistant",
        content: "임플란트는 ...",
        status: "complete",
        qaLogId: 202,
      }),
    ];

    expect(resolveRetryTarget(legacy, "aA")!.historyTurnIds).toEqual([]);
  });

  it("빈 배열 스냅샷은 '없음' 이 아니라 '맥락 0턴' 으로 읽는다", () => {
    // historyTurnIds: [] 가 있으면 폴백 계산을 하지 않는다.
    const conversation: QAMessage[] = [
      msg({ id: "u0", role: "user", content: "앞 질문" }),
      msg({
        id: "a0",
        role: "assistant",
        content: "앞 답변",
        status: "complete",
        qaLogId: 101,
      }),
      msg({ id: "uA", role: "user", content: "재시도 대상" }),
      msg({
        id: "aA",
        role: "assistant",
        content: "",
        status: "error",
        historyTurnIds: [],
      }),
    ];

    const target = resolveRetryTarget(conversation, "aA")!;
    expect(target.fromSnapshot).toBe(true);
    expect(target.historyTurnIds).toEqual([]);
  });

  it("스냅샷 배열을 복사해서 돌려준다 (스토어 상태 오염 방지)", () => {
    const target = resolveRetryTarget(A_ERROR_THEN_B_OK, "aA")!;
    target.historyTurnIds.push(999);

    expect(
      A_ERROR_THEN_B_OK.find((m) => m.id === "aA")!.historyTurnIds,
    ).toEqual([]);
  });

  it("찾을 수 없는 대상은 null", () => {
    expect(resolveRetryTarget(A_ERROR_THEN_B_OK, "없음")).toBeNull();
    expect(resolveRetryTarget(A_ERROR_THEN_B_OK, "uA")).toBeNull();
  });
});

describe("historyTurnIdsBefore", () => {
  it("오류·미완료 턴과 로그 id 없는 턴은 제외한다", () => {
    const conversation: QAMessage[] = [
      msg({ id: "u0", role: "user", content: "정상 질문" }),
      msg({
        id: "a0",
        role: "assistant",
        content: "정상 답변",
        status: "complete",
        qaLogId: 101,
      }),
      msg({ id: "u1", role: "user", content: "끊긴 질문" }),
      msg({ id: "a1", role: "assistant", content: "반쪽", status: "error" }),
      msg({ id: "u2", role: "user", content: "로그 id 없는 턴" }),
      msg({ id: "a2", role: "assistant", content: "답변", status: "complete" }),
      msg({ id: "uT", role: "user", content: "재시도 대상" }),
      msg({ id: "aT", role: "assistant", content: "", status: "error" }),
    ];

    expect(historyTurnIdsBefore(conversation, "aT")).toEqual([101]);
  });

  it("첫 턴이면 빈 목록", () => {
    const conversation: QAMessage[] = [
      msg({ id: "uT", role: "user", content: "첫 질문" }),
      msg({ id: "aT", role: "assistant", content: "", status: "error" }),
    ];
    expect(historyTurnIdsBefore(conversation, "aT")).toEqual([]);
  });

  it("없는 id 면 빈 목록", () => {
    expect(historyTurnIdsBefore([], "없음")).toEqual([]);
  });
});
