import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KnowledgeFileTable } from "../KnowledgeFileTable";

vi.mock("../../api/knowledge", () => ({
  fetchKnowledgeList: vi.fn(),
}));

function makeItem(overrides: Partial<{
  id: number; filename: string; status: string; chunk_count: number | null; category_count: number | null;
}> = {}) {
  return {
    id: 1,
    filename: "test.txt",
    uploaded_at: "2026-04-28T12:00:00+09:00",
    size_bytes: 1024,
    chunk_count: 5,
    category_count: 2,
    status: "validated",
    uploaded_by_admin_id: 99,
    ...overrides,
  };
}

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("KnowledgeFileTable", () => {
  it("빈 상태 카피 렌더", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });

    renderWithQuery(<KnowledgeFileTable />);
    expect(await screen.findByText(/첫 TXT 파일을 업로드해보세요/)).toBeDefined();
  });

  it("validated 상태 → '재벡터화 대기' 뱃지", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem({ status: "validated" })],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<KnowledgeFileTable />);
    expect(await screen.findByText("재벡터화 대기")).toBeDefined();
  });

  it("active 상태 → '활성' 뱃지", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem({ status: "active" })],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<KnowledgeFileTable />);
    expect(await screen.findByText("활성")).toBeDefined();
  });

  it("deleted 상태 → '삭제됨' 뱃지", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem({ status: "deleted" })],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<KnowledgeFileTable />);
    expect(await screen.findByText("삭제됨")).toBeDefined();
  });

  it("파일명·청크수·분류수 렌더", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem({ filename: "치과지식.txt", chunk_count: 42, category_count: 5 })],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<KnowledgeFileTable />);
    expect(await screen.findByText("치과지식.txt")).toBeDefined();
    expect(await screen.findByText("42")).toBeDefined();
    expect(await screen.findByText("5")).toBeDefined();
  });

  it("초기 목록에 validated 2건이면 onValidatedCountChange(2) 호출", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [
        makeItem({ id: 1, status: "validated" }),
        makeItem({ id: 2, status: "validated" }),
        makeItem({ id: 3, status: "active" }),
      ],
      page: 1,
      per_page: 20,
      total: 3,
    });

    const onValidatedCountChange = vi.fn();
    renderWithQuery(<KnowledgeFileTable onValidatedCountChange={onValidatedCountChange} />);
    await screen.findByText("활성");
    expect(onValidatedCountChange).toHaveBeenCalledWith(2);
  });

  it("편집/삭제 버튼에 disabled 속성 없음 (Story 8.2 활성화)", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem()],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<KnowledgeFileTable />);
    const buttons = await screen.findAllByRole("button");
    const actionBtns = buttons.filter((b) =>
      b.textContent === "편집" || b.textContent === "삭제",
    );
    expect(actionBtns.length).toBe(2);
    actionBtns.forEach((btn) => expect((btn as HTMLButtonElement).disabled).toBe(false));
  });

  it("편집 버튼 클릭 → onEdit 콜백 호출 (인자 item.id)", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeItem({ id: 42 })],
      page: 1,
      per_page: 20,
      total: 1,
    });

    const onEdit = vi.fn();
    renderWithQuery(<KnowledgeFileTable onEdit={onEdit} />);
    const editBtn = await screen.findByText("편집");
    editBtn.click();
    expect(onEdit).toHaveBeenCalledWith(42);
  });

  it("삭제 버튼 클릭 → onDelete 콜백 호출 (인자 item)", async () => {
    const { fetchKnowledgeList } = await import("../../api/knowledge");
    const item = makeItem({ id: 7, filename: "삭제대상.txt" });
    (fetchKnowledgeList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [item],
      page: 1,
      per_page: 20,
      total: 1,
    });

    const onDelete = vi.fn();
    renderWithQuery(<KnowledgeFileTable onDelete={onDelete} />);
    const deleteBtn = await screen.findByText("삭제");
    deleteBtn.click();
    expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 7, filename: "삭제대상.txt" }));
  });
});
