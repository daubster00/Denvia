import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { KnowledgeFileEditDialog } from "../KnowledgeFileEditDialog";

vi.mock("../../api/knowledge", () => ({
  fetchKnowledgeDetail: vi.fn(),
  editKnowledge: vi.fn(),
}));

const defaultProps = {
  uploadId: 1,
  onClose: vi.fn(),
  onSaved: vi.fn(),
};

describe("KnowledgeFileEditDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetchKnowledgeDetail 응답 content가 textarea value에 존재", async () => {
    const { fetchKnowledgeDetail } = await import("../../api/knowledge");
    (fetchKnowledgeDetail as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 1,
      filename: "치과지식.txt",
      content: "{보철}\n=크라운=\n본문\n",
      uploaded_at: "",
      last_modified_at: "",
      size_bytes: 100,
      chunk_count: 1,
      category_count: 1,
      status: "validated",
    });

    render(<KnowledgeFileEditDialog {...defaultProps} />);

    const textarea = await screen.findByRole<HTMLTextAreaElement>("textbox");
    expect(textarea.value).toContain("{보철}");
    expect(textarea.value).toContain("=크라운=");
  });

  it("[저장] 클릭 → editKnowledge 호출 + onSaved + onClose", async () => {
    const { fetchKnowledgeDetail, editKnowledge } = await import("../../api/knowledge");
    (fetchKnowledgeDetail as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 1,
      filename: "test.txt",
      content: "{보철}\n=크라운=\n내용\n",
      uploaded_at: "",
      last_modified_at: "",
      size_bytes: 50,
      chunk_count: 1,
      category_count: 1,
      status: "validated",
    });
    (editKnowledge as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 1,
      filename: "test.txt",
      size_bytes: 50,
      chunk_count: 1,
      category_count: 1,
      status: "validated",
      last_modified_at: "",
    });

    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(
      <KnowledgeFileEditDialog uploadId={1} onClose={onClose} onSaved={onSaved} />,
    );

    await screen.findByRole("textbox");

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(editKnowledge).toHaveBeenCalledWith(1, expect.any(String));
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("editKnowledge 422 에러 → 에러 메시지 렌더", async () => {
    const { fetchKnowledgeDetail, editKnowledge } = await import("../../api/knowledge");
    (fetchKnowledgeDetail as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 1,
      filename: "test.txt",
      content: "{보철}\n=크라운=\n내용\n",
      uploaded_at: "",
      last_modified_at: "",
      size_bytes: 50,
      chunk_count: 1,
      category_count: 1,
      status: "validated",
    });
    (editKnowledge as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("파싱 불가능한 포맷입니다."),
    );

    render(<KnowledgeFileEditDialog {...defaultProps} />);
    await screen.findByRole("textbox");

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    expect(await screen.findByText("파싱 불가능한 포맷입니다.")).toBeDefined();
  });

  it("ESC 키 → onClose 호출", async () => {
    const { fetchKnowledgeDetail } = await import("../../api/knowledge");
    (fetchKnowledgeDetail as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 1,
      filename: "test.txt",
      content: "내용",
      uploaded_at: "",
      last_modified_at: "",
      size_bytes: 10,
      chunk_count: 0,
      category_count: 0,
      status: "validated",
    });

    const onClose = vi.fn();
    render(<KnowledgeFileEditDialog uploadId={1} onClose={onClose} onSaved={vi.fn()} />);
    await screen.findByRole("dialog");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
