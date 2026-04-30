import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PromptBlockCard } from "../PromptBlockCard";

vi.mock("../../api/prompts", () => ({
  updatePromptBlock: vi.fn(),
  promptUpdateSchema: {
    parse: vi.fn(),
  },
}));

vi.mock("@hookform/resolvers/zod", () => ({
  zodResolver: () => async (values: unknown) => ({ values, errors: {} }),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const mockBlock = {
  block_id: "BASE",
  trigger_keywords: [],
  content: "기본 프롬프트 내용",
  enabled: true,
  updated_at: "2026-04-28T00:00:00Z",
};

const mockBlockWithKeywords = {
  block_id: "치식_위치",
  trigger_keywords: ["치식", "상악", "하악"],
  content: "치식 관련 내용",
  enabled: true,
  updated_at: "2026-04-28T00:00:00Z",
};

describe("PromptBlockCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("초기 렌더: Accordion 헤더만 보임, 본문 숨김", () => {
    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    expect(screen.getByText("BASE")).toBeDefined();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("헤더 클릭 → Accordion 펼침, textarea와 체크박스 렌더", () => {
    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);
    expect(screen.getByRole("textbox")).toBeDefined();
    expect(screen.getByRole("checkbox")).toBeDefined();
  });

  it("트리거 키워드 Chip 렌더 (keywords가 있을 때)", () => {
    renderWithQuery(<PromptBlockCard block={mockBlockWithKeywords} />);
    const header = screen.getByText("치식_위치").closest("button")!;
    fireEvent.click(header);
    expect(screen.getByText("치식")).toBeDefined();
    expect(screen.getByText("상악")).toBeDefined();
  });

  it("BASE 블록 — trigger_keywords 빈 배열이면 Chip 없음", () => {
    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);
    expect(screen.queryByText("치식")).toBeNull();
  });

  it("[저장] 클릭 → ConfirmDialog 오픈", async () => {
    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "수정된 내용" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?")).toBeDefined();
    });
  });

  it("ConfirmDialog 취소 → API 호출 없음", async () => {
    const { updatePromptBlock } = await import("../../api/prompts");

    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "수정된 내용" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?");
    });

    // ConfirmDialog의 취소 버튼 (폼 취소 버튼과 구분)
    const cancelBtns = screen.getAllByText("취소");
    fireEvent.click(cancelBtns[cancelBtns.length - 1]);

    expect(updatePromptBlock).not.toHaveBeenCalled();
  });

  it("ConfirmDialog 확인 → updatePromptBlock 호출", async () => {
    const { updatePromptBlock } = await import("../../api/prompts");
    (updatePromptBlock as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);

    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "수정된 내용" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?");
    });

    // ConfirmDialog의 확인 버튼
    const confirmBtns = screen.getAllByText("저장");
    // confirmLabel="저장"이 ConfirmDialog 내부 확인 버튼에도 있음
    fireEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => {
      expect(updatePromptBlock).toHaveBeenCalled();
    });
  });

  it("[취소] 버튼 클릭 → 폼 reset", () => {
    renderWithQuery(<PromptBlockCard block={mockBlock} />);
    const header = screen.getByText("BASE").closest("button")!;
    fireEvent.click(header);

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "수정된 내용" } });

    const cancelBtn = screen.getByText("취소");
    fireEvent.click(cancelBtn);

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("기본 프롬프트 내용");
  });
});
