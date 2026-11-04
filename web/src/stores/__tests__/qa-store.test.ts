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


describe("pruneGhostTurns — 대화 누적 모드의 유령 턴 청소 (#149)", () => {
  const msg = (
    id: string,
    role: "user" | "assistant",
    status: "complete" | "pending" | "error",
    content = "",
  ) => ({
    id,
    role,
    status,
    content,
    timestamp: "2026-01-01T00:00:00.000Z",
  });

  it("빈 pending 답변은 직전 질문과 함께 제거한다", () => {
    useQAStore.setState({
      messages: [msg("1", "user", "complete", "질문A"), msg("2", "assistant", "pending", "")],
    });
    useQAStore.getState().pruneGhostTurns();
    expect(useQAStore.getState().messages).toEqual([]);
  });

  // 검수 P1-3 — 예전에는 내용이 있는 pending 답변을 complete(정상 완료)로 승격했다.
  // 그러면 반쪽 답변이 "신뢰된 과거 대화"가 되어 다음 질문의 맥락으로 올라간다.
  // 화면에는 보존하되 **중단 상태(error)** 로 남겨야 한다.
  it("내용이 있는 pending 답변은 중단 상태로 남기고 정상 완료로 승격하지 않는다", () => {
    useQAStore.setState({
      messages: [msg("1", "user", "complete", "질문A"), msg("2", "assistant", "pending", "답변 일부")],
    });
    useQAStore.getState().pruneGhostTurns();
    const after = useQAStore.getState().messages;
    expect(after).toHaveLength(2);
    expect(after[1].status).toBe("error");
    expect(after[1].content).toBe("답변 일부");  // 받은 글자는 지우지 않는다
    expect(after[1].errorMessage).toBeTruthy();
  });

  it("정상 대화는 건드리지 않는다", () => {
    const before = [
      msg("1", "user", "complete", "질문A"),
      msg("2", "assistant", "complete", "답변A"),
    ];
    useQAStore.setState({ messages: before });
    useQAStore.getState().pruneGhostTurns();
    expect(useQAStore.getState().messages).toEqual(before);
  });

  it("유령 턴만 걷어내고 완료된 과거 대화는 보존한다", () => {
    useQAStore.setState({
      messages: [
        msg("1", "user", "complete", "질문A"),
        msg("2", "assistant", "complete", "답변A"),
        msg("3", "user", "complete", "질문B"),
        msg("4", "assistant", "pending", ""),
      ],
    });
    useQAStore.getState().pruneGhostTurns();
    const after = useQAStore.getState().messages;
    expect(after.map((m) => m.id)).toEqual(["1", "2"]);
  });

  it("에러 상태 답변은 그대로 둔다", () => {
    const before = [
      msg("1", "user", "complete", "질문A"),
      msg("2", "assistant", "error", ""),
    ];
    useQAStore.setState({ messages: before });
    useQAStore.getState().pruneGhostTurns();
    expect(useQAStore.getState().messages).toEqual(before);
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 2026-11-03 검수 P0-4 — 로그아웃·계정 전환 시 이전 사용자의 대화가 남으면 안 된다
// ──────────────────────────────────────────────────────────────────────────────

describe("세션 소유자 전환 (검수 P0-4)", () => {
  const turn = (id: string, role: "user" | "assistant", content: string) => ({
    id,
    role,
    status: "complete" as const,
    content,
    timestamp: "2026-01-01T00:00:00.000Z",
  });

  beforeEach(() => {
    useQAStore.setState({
      messages: [],
      pendingHomeQuestion: null,
      ownerUserId: null,
    });
  });

  it("처음 로그인한 사용자를 주인으로 기록하고 대화는 건드리지 않는다", () => {
    useQAStore.setState({ messages: [turn("1", "user", "질문A")] });
    useQAStore.getState().setOwner(10);
    expect(useQAStore.getState().ownerUserId).toBe(10);
    expect(useQAStore.getState().messages).toHaveLength(1);
  });

  it("같은 사용자의 새로고침·페이지 이동에서는 대화를 유지한다", () => {
    useQAStore.setState({ messages: [turn("1", "user", "질문A")], ownerUserId: 10 });
    useQAStore.getState().setOwner(10);
    expect(useQAStore.getState().messages).toHaveLength(1);
  });

  it("다른 계정이 들어오면 이전 사용자의 대화와 대기 질문을 즉시 비운다", () => {
    useQAStore.setState({
      messages: [turn("1", "user", "A의 질문"), turn("2", "assistant", "A의 답변")],
      pendingHomeQuestion: "A의 대기 질문",
      ownerUserId: 10,
    });
    useQAStore.getState().setOwner(20);
    const s = useQAStore.getState();
    expect(s.ownerUserId).toBe(20);
    expect(s.messages).toEqual([]);
    expect(s.pendingHomeQuestion).toBeNull();
  });

  it("세션 종료(로그아웃·강제 종료)는 대화·대기 질문·주인 정보를 모두 비운다", () => {
    useQAStore.setState({
      messages: [turn("1", "user", "질문")],
      pendingHomeQuestion: "대기",
      ownerUserId: 10,
    });
    useQAStore.getState().resetForSessionEnd();
    const s = useQAStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.pendingHomeQuestion).toBeNull();
    expect(s.ownerUserId).toBeNull();
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 2026-11-03 검수 P1-5 — 한도 거절(429)에서 과거 정상 대화는 보존해야 한다
// ──────────────────────────────────────────────────────────────────────────────

describe("dropTurn — 이번 턴만 걷어내기 (검수 P1-5)", () => {
  const m = (id: string, role: "user" | "assistant", content: string, status: "complete" | "pending" = "complete") => ({
    id,
    role,
    status,
    content,
    timestamp: "2026-01-01T00:00:00.000Z",
  });

  it("거절된 질문·빈 답변만 제거하고 과거 대화는 그대로 남긴다", () => {
    useQAStore.setState({
      messages: [
        m("1", "user", "질문A"),
        m("2", "assistant", "답변A"),
        m("3", "user", "질문B"),
        m("4", "assistant", "", "pending"),
      ],
    });
    useQAStore.getState().dropTurn("4");
    expect(useQAStore.getState().messages.map((x) => x.id)).toEqual(["1", "2"]);
  });

  it("없는 id 는 아무것도 바꾸지 않는다", () => {
    const before = [m("1", "user", "질문A"), m("2", "assistant", "답변A")];
    useQAStore.setState({ messages: before });
    useQAStore.getState().dropTurn("nope");
    expect(useQAStore.getState().messages).toEqual(before);
  });
});
