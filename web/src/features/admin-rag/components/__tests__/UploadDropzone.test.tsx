import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { UploadDropzone } from "../UploadDropzone";

vi.mock("../../api/knowledge", () => ({
  uploadKnowledge: vi.fn(),
}));

const onSuccess = vi.fn();
const onHighlightDuplicate = vi.fn();

function makeFile(name: string, size: number, type: string): File {
  const content = new Uint8Array(size).fill(65); // 'A'
  return new File([content], name, { type });
}

describe("UploadDropzone", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("드롭존이 렌더된다", () => {
    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);
    expect(screen.getByRole("button")).toBeDefined();
  });

  it("10MB 초과 파일 → 에러 메시지 표시 (서버 호출 없음)", async () => {
    const { uploadKnowledge } = await import("../../api/knowledge");
    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    const bigFile = makeFile("big.txt", 11 * 1024 * 1024, "text/plain");

    Object.defineProperty(input, "files", { value: [bigFile], configurable: true });
    fireEvent.change(input);

    const error = await screen.findByRole("alert");
    expect(error.textContent).toContain("10MB");
    expect(uploadKnowledge).not.toHaveBeenCalled();
  });

  it(".txt 아닌 확장자 → 에러 메시지 표시", async () => {
    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    const docxFile = makeFile("doc.docx", 1000, "text/plain");

    Object.defineProperty(input, "files", { value: [docxFile], configurable: true });
    fireEvent.change(input);

    const error = await screen.findByRole("alert");
    expect(error.textContent).toContain(".txt");
  });

  it("드롭 이벤트로 파일 전달됨", async () => {
    const { uploadKnowledge } = await import("../../api/knowledge");
    (uploadKnowledge as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      upload_id: 1,
      filename: "test.txt",
      size_bytes: 100,
      chunk_count: 2,
      category_count: 1,
      hierarchy_preview: [],
    });

    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);
    const dropzone = screen.getByRole("button");

    const txtFile = makeFile("test.txt", 100, "text/plain");
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [txtFile] },
    });

    // 서버 호출 됨 (파일 크기·확장자 통과)
    expect(uploadKnowledge).toHaveBeenCalled();
  });

  it("여러 파일 선택 시 모두 순차 업로드 + 마지막 응답으로 onSuccess 1회 호출", async () => {
    const { uploadKnowledge } = await import("../../api/knowledge");
    (uploadKnowledge as ReturnType<typeof vi.fn>).mockImplementation(
      (file: File) =>
        Promise.resolve({
          upload_id: file.name === "a.txt" ? 1 : 2,
          filename: file.name,
          size_bytes: file.size,
          chunk_count: 1,
          category_count: 1,
          hierarchy_preview: [],
        }),
    );

    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    expect(input.multiple).toBe(true);

    const f1 = makeFile("a.txt", 100, "text/plain");
    const f2 = makeFile("b.txt", 200, "text/plain");

    Object.defineProperty(input, "files", { value: [f1, f2], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect((uploadKnowledge as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
    });
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
    const lastResp = onSuccess.mock.calls[0][0];
    expect(lastResp.filename).toBe("b.txt");
  });

  it("Enter/Space 키보드 트리거 → input click", () => {
    render(<UploadDropzone onSuccess={onSuccess} onHighlightDuplicate={onHighlightDuplicate} />);
    const dropzone = screen.getByRole("button");
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    const clickSpy = vi.spyOn(input, "click");

    const before = clickSpy.mock.calls.length;
    fireEvent.keyDown(dropzone, { key: "Enter" });
    const afterEnter = clickSpy.mock.calls.length;
    // Enter 키 후 input.click이 최소 1번 이상 호출됨
    expect(afterEnter).toBeGreaterThan(before);

    const before2 = clickSpy.mock.calls.length;
    fireEvent.keyDown(dropzone, { key: " " });
    const afterSpace = clickSpy.mock.calls.length;
    // Space 키 후 추가 호출 확인
    expect(afterSpace).toBeGreaterThan(before2);
  });
});
