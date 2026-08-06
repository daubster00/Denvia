import { describe, it, expect, beforeEach } from "vitest";
import { useQAStore } from "../qa-store";

const EMPTY_STATE = {
  messages: [],
};

function resetStore() {
  useQAStore.setState(EMPTY_STATE);
}

beforeEach(() => {
  resetStore();
});

describe("useQAStore — 기존 액션", () => {
  it("addMessage가 메시지를 추가한다", () => {
    const msg = {
      id: "1",
      role: "user" as const,
      content: "임플란트 보험",
      status: "complete" as const,
      timestamp: "2026-01-01T00:00:00.000Z",
    };
    useQAStore.getState().addMessage(msg);
    expect(useQAStore.getState().messages).toHaveLength(1);
    expect(useQAStore.getState().messages[0].content).toBe("임플란트 보험");
  });

  it("clearMessages가 모든 메시지를 제거한다", () => {
    useQAStore.getState().addMessage({
      id: "1",
      role: "user",
      content: "test",
      status: "complete",
      timestamp: "2026-01-01T00:00:00.000Z",
    });
    useQAStore.getState().clearMessages();
    expect(useQAStore.getState().messages).toHaveLength(0);
  });
});

describe("useQAStore — 신규 액션 (Story 2.2)", () => {
  const ASSISTANT_ID = "asst-1";

  beforeEach(() => {
    useQAStore.getState().addMessage({
      id: ASSISTANT_ID,
      role: "assistant",
      content: "",
      status: "pending",
      timestamp: "2026-01-01T00:00:00.000Z",
    });
  });

  it("addToken이 content에 delta를 누적한다", () => {
    useQAStore.getState().addToken(ASSISTANT_ID, "안녕");
    useQAStore.getState().addToken(ASSISTANT_ID, "하세요");
    const msg = useQAStore.getState().messages.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.content).toBe("안녕하세요");
  });

  it("markRuleMatched가 ruleMatched와 procedureCount를 설정한다", () => {
    useQAStore.getState().markRuleMatched(ASSISTANT_ID, 2);
    const msg = useQAStore.getState().messages.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.ruleMatched).toBe(true);
    expect(msg?.procedureCount).toBe(2);
  });

  it("finalize가 qaLogId를 설정하고 status를 complete로 변경한다", () => {
    useQAStore.getState().finalize(ASSISTANT_ID, 99);
    const msg = useQAStore.getState().messages.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.qaLogId).toBe(99);
    expect(msg?.status).toBe("complete");
  });

  it("setError가 부분 답변(content)은 보존하고 errorMessage/status만 설정한다 (#141)", () => {
    // 끊기기 전까지 받은 부분 답변이 있는 상태
    useQAStore.getState().addToken(ASSISTANT_ID, "임플란트는");
    useQAStore.getState().setError(ASSISTANT_ID, "인터넷 연결이 끊겨 답변이 중단됐어요.");
    const msg = useQAStore.getState().messages.find((m) => m.id === ASSISTANT_ID);
    // content 는 지워지지 않고 그대로 남아 있어야 한다 (과거엔 에러 문구로 교체됐음)
    expect(msg?.content).toBe("임플란트는");
    expect(msg?.errorMessage).toBe("인터넷 연결이 끊겨 답변이 중단됐어요.");
    expect(msg?.status).toBe("error");
  });

  it("addToken이 다른 ID의 메시지를 수정하지 않는다", () => {
    useQAStore.getState().addMessage({
      id: "other",
      role: "user",
      content: "기존 메시지",
      status: "complete",
      timestamp: "2026-01-01T00:00:00.000Z",
    });
    useQAStore.getState().addToken(ASSISTANT_ID, "토큰");
    const other = useQAStore.getState().messages.find((m) => m.id === "other");
    expect(other?.content).toBe("기존 메시지");
  });
});

