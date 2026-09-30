/**
 * ChatMessage — 기다리는 동안 안내 문구가 단계적으로 바뀌는지 (2026-09-30 장애 후속).
 *
 * 문구가 한 번 뜨고 멈춰 있으면 화면이 굳은 것처럼 보인다. 그날 한 사용자가 같은
 * 질문을 3번 다시 던졌다. 시간이 지날수록 말이 바뀌는지를 본다.
 */

import { render, screen, act } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { ChatMessage } from "../ChatMessage";
import type { QAMessage } from "@/stores/qa-store";

function pendingMessage(): QAMessage {
  return {
    id: "a1",
    role: "assistant",
    content: "",
    status: "pending",
  } as QAMessage;
}

describe("ChatMessage 대기 안내", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("처음에는 '생각중이야'만 보이고 추가 안내는 없다", () => {
    render(<ChatMessage message={pendingMessage()} />);

    expect(screen.getByText("생각중이야…")).toBeDefined();
    expect(screen.queryByText(/시간이 더 걸립니다/)).toBeNull();
  });

  it("7초·15초·30초를 지나며 안내 문구가 바뀐다", () => {
    render(<ChatMessage message={pendingMessage()} />);

    act(() => {
      vi.advanceTimersByTime(7000);
    });
    expect(screen.getByText("복잡한 질문은 시간이 더 걸립니다.")).toBeDefined();

    act(() => {
      vi.advanceTimersByTime(8000); // 누적 15초
    });
    expect(
      screen.getByText("자료를 찾아보고 있어요. 조금만 기다려 주세요.")
    ).toBeDefined();
    expect(screen.queryByText(/시간이 더 걸립니다/)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(15000); // 누적 30초
    });
    expect(
      screen.getByText("평소보다 오래 걸리고 있어요. 곧 답변이 시작됩니다.")
    ).toBeDefined();
  });

  it("실패하면 서버가 내려준 안내 문구를 그대로 보여준다", () => {
    const failed = {
      ...pendingMessage(),
      status: "error",
      errorMessage: "답변이 시작되지 않아 중단했어요. 일시적인 지연일 수 있으니 잠시 후 다시 시도해주세요.",
    } as QAMessage;

    render(<ChatMessage message={failed} />);

    expect(screen.getByText(/답변이 시작되지 않아 중단했어요/)).toBeDefined();
    // 사용자 탓으로 읽히는 옛 문구가 되살아나지 않게 못을 박는다
    expect(screen.queryByText(/질문이 복잡해/)).toBeNull();
  });
});
