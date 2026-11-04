/**
 * 오류 답변 재시도 대상 — 2026-11-03 검수 P1-6.
 * 어떤 답변의 "다시 시도" 를 눌렀는지에 따라 **그 답변의 원 질문**이 다시 전송돼야 한다.
 */
import { describe, expect, it } from "vitest";
import { resolveRetryQuestion } from "@/features/qa/lib/retry-target";
import type { QAMessage } from "@/stores/qa-store";

const m = (
  id: string,
  role: "user" | "assistant",
  content: string,
  status: QAMessage["status"] = "complete",
): QAMessage => ({
  id,
  role,
  content,
  status,
  timestamp: "2026-01-01T00:00:00.000Z",
});

const CONVERSATION: QAMessage[] = [
  m("u1", "user", "스케일링 산정 기준"),
  m("a1", "assistant", "", "error"),
  m("u2", "user", "임플란트 보험 적용 조건"),
  m("a2", "assistant", "답변", "complete"),
  m("u3", "user", "틀니 본인부담금"),
  m("a3", "assistant", "", "error"),
];

describe("resolveRetryQuestion", () => {
  it("위쪽 오류 답변을 누르면 그 답변의 원 질문을 돌려준다", () => {
    expect(resolveRetryQuestion(CONVERSATION, "a1")).toBe("스케일링 산정 기준");
  });

  it("가장 최근 질문이 아니라 **누른 답변**의 질문이어야 한다", () => {
    expect(resolveRetryQuestion(CONVERSATION, "a1")).not.toBe("틀니 본인부담금");
  });

  it("마지막 오류 답변은 마지막 질문을 돌려준다", () => {
    expect(resolveRetryQuestion(CONVERSATION, "a3")).toBe("틀니 본인부담금");
  });

  it("없는 id · 첫 메시지 · 사용자 메시지면 null (아무것도 보내지 않는다)", () => {
    expect(resolveRetryQuestion(CONVERSATION, "없음")).toBeNull();
    expect(resolveRetryQuestion(CONVERSATION, "u1")).toBeNull();
    expect(resolveRetryQuestion([m("a0", "assistant", "", "error")], "a0")).toBeNull();
  });

  it("질문이 공백뿐이면 null", () => {
    const msgs = [m("u", "user", "   "), m("a", "assistant", "", "error")];
    expect(resolveRetryQuestion(msgs, "a")).toBeNull();
  });
});
