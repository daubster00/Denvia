import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

// Tiptap을 jsdom에서 그대로 부트스트랩하면 prosemirror가 ResizeObserver/range API
// 등을 요구해 매우 느려진다. 본 테스트는 RichTextEditor 컴포넌트의 툴바·prompt
// 검증 로직만 다루므로 useEditor를 가벼운 mock 객체로 대체한다.

type MockChain = ReturnType<typeof makeChain>;

function makeChain() {
  const chain = {
    toggleBold: vi.fn().mockReturnThis(),
    toggleItalic: vi.fn().mockReturnThis(),
    toggleUnderline: vi.fn().mockReturnThis(),
    toggleBulletList: vi.fn().mockReturnThis(),
    toggleOrderedList: vi.fn().mockReturnThis(),
    setLink: vi.fn().mockReturnThis(),
    setImage: vi.fn().mockReturnThis(),
    focus: vi.fn().mockReturnThis(),
    run: vi.fn(),
  };
  return chain;
}

let mockChain: MockChain;

vi.mock("@tiptap/react", () => ({
  useEditor: () => ({
    isActive: vi.fn().mockReturnValue(false),
    chain: () => mockChain,
    getHTML: vi.fn().mockReturnValue(""),
    commands: {
      setContent: vi.fn(),
    },
  }),
  EditorContent: ({ className }: { className?: string }) => (
    <div data-testid="editor-content" className={className} />
  ),
}));

vi.mock("@tiptap/starter-kit", () => ({ default: {} }));
vi.mock("@tiptap/extension-link", () => ({
  default: { configure: () => ({}) },
}));
vi.mock("@tiptap/extension-image", () => ({
  default: { configure: () => ({}) },
}));

import { RichTextEditor } from "../RichTextEditor";

describe("RichTextEditor", () => {
  beforeEach(() => {
    mockChain = makeChain();
    cleanup();
    vi.spyOn(window, "prompt");
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  it("툴바 6종 + 링크/이미지 버튼이 모두 렌더된다", () => {
    render(<RichTextEditor value="" onChange={() => {}} />);
    expect(screen.getByRole("toolbar")).toBeDefined();
    expect(screen.getByLabelText("굵게")).toBeDefined();
    expect(screen.getByLabelText("기울임")).toBeDefined();
    expect(screen.getByLabelText("밑줄")).toBeDefined();
    expect(screen.getByLabelText("글머리 기호 목록")).toBeDefined();
    expect(screen.getByLabelText("번호 매기기 목록")).toBeDefined();
    expect(screen.getByLabelText("링크 삽입")).toBeDefined();
    expect(screen.getByLabelText("이미지 삽입")).toBeDefined();
  });

  it("굵게/기울임/밑줄 클릭 → editor.chain().toggle*().run() 호출", () => {
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("굵게"));
    expect(mockChain.toggleBold).toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("기울임"));
    expect(mockChain.toggleItalic).toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("밑줄"));
    expect(mockChain.toggleUnderline).toHaveBeenCalled();
  });

  it("리스트 버튼 클릭 → toggleBulletList / toggleOrderedList", () => {
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("글머리 기호 목록"));
    expect(mockChain.toggleBulletList).toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("번호 매기기 목록"));
    expect(mockChain.toggleOrderedList).toHaveBeenCalled();
  });

  it("링크 prompt — https URL 입력 시 setLink 호출", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "https://example.com"
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(mockChain.setLink).toHaveBeenCalledWith({
      href: "https://example.com",
    });
  });

  it("링크 prompt — javascript: URL 입력 시 alert + setLink 호출 안 함", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "javascript:alert(1)"
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(window.alert).toHaveBeenCalled();
    expect(mockChain.setLink).not.toHaveBeenCalled();
  });

  it("링크 prompt — mailto: URL 입력 시 alert + setLink 호출 안 함 (이메일 0건 정책)", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "mailto:user@example.com"
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(window.alert).toHaveBeenCalled();
    expect(mockChain.setLink).not.toHaveBeenCalled();
  });

  it("이미지 prompt — https URL 입력 시 setImage 호출", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "https://cdn.example.com/x.png"
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("이미지 삽입"));
    expect(mockChain.setImage).toHaveBeenCalledWith({
      src: "https://cdn.example.com/x.png",
    });
  });

  it("이미지 prompt — data: URL 입력 시 alert + setImage 호출 안 함", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "data:image/svg+xml;base64,abc"
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("이미지 삽입"));
    expect(window.alert).toHaveBeenCalled();
    expect(mockChain.setImage).not.toHaveBeenCalled();
  });

  it("prompt 취소(null) → setLink/setImage 호출 안 함", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(null);
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    fireEvent.click(screen.getByLabelText("이미지 삽입"));
    expect(mockChain.setLink).not.toHaveBeenCalled();
    expect(mockChain.setImage).not.toHaveBeenCalled();
  });
});
