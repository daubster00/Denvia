import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";

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
    setColor: vi.fn().mockReturnThis(),
    unsetColor: vi.fn().mockReturnThis(),
    setFontSize: vi.fn().mockReturnThis(),
    unsetFontSize: vi.fn().mockReturnThis(),
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
    getAttributes: vi.fn().mockReturnValue({}),
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
vi.mock("@tiptap/extension-text-style", () => ({
  TextStyle: {},
  Color: {},
  FontSize: {},
}));

import { RichTextEditor } from "../RichTextEditor";

describe("RichTextEditor", () => {
  beforeEach(() => {
    mockChain = makeChain();
    cleanup();
    vi.spyOn(window, "prompt");
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  it("툴바 5종 + 링크 버튼이 렌더된다 (이미지 버튼은 onImageUpload 없을 때 숨김)", () => {
    render(<RichTextEditor value="" onChange={() => {}} />);
    expect(screen.getByRole("toolbar")).toBeDefined();
    expect(screen.getByLabelText("굵게")).toBeDefined();
    expect(screen.getByLabelText("기울임")).toBeDefined();
    expect(screen.getByLabelText("밑줄")).toBeDefined();
    expect(screen.getByLabelText("글머리 기호 목록")).toBeDefined();
    expect(screen.getByLabelText("번호 매기기 목록")).toBeDefined();
    expect(screen.getByLabelText("링크 삽입")).toBeDefined();
    expect(screen.queryByLabelText("이미지 삽입")).toBeNull();
  });

  it("onImageUpload 가 주입되면 이미지 삽입 버튼이 보인다", () => {
    render(
      <RichTextEditor
        value=""
        onChange={() => {}}
        onImageUpload={async () => "/static/x.png"}
      />,
    );
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
      "https://example.com",
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(mockChain.setLink).toHaveBeenCalledWith({
      href: "https://example.com",
    });
  });

  it("링크 prompt — javascript: URL 입력 시 alert + setLink 호출 안 함", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "javascript:alert(1)",
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(window.alert).toHaveBeenCalled();
    expect(mockChain.setLink).not.toHaveBeenCalled();
  });

  it("링크 prompt — mailto: URL 입력 시 alert + setLink 호출 안 함 (이메일 0건 정책)", () => {
    (window.prompt as ReturnType<typeof vi.fn>).mockReturnValue(
      "mailto:user@example.com",
    );
    render(<RichTextEditor value="" onChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("링크 삽입"));
    expect(window.alert).toHaveBeenCalled();
    expect(mockChain.setLink).not.toHaveBeenCalled();
  });

  it("이미지 버튼 → 파일 선택 → onImageUpload 호출 후 setImage 로 src 삽입", async () => {
    const onImageUpload = vi
      .fn()
      .mockResolvedValue("/static/popup-images/abc.png");
    render(
      <RichTextEditor
        value=""
        onChange={() => {}}
        onImageUpload={onImageUpload}
      />,
    );

    const file = new File(["x"], "x.png", { type: "image/png" });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(onImageUpload).toHaveBeenCalledWith(file),
    );
    // 백엔드 상대경로 `/static/...` 는 에디터 안에서 API 서버 absolute URL 로 변환된다.
    // (웹앱 origin 과 API 서버 origin 이 분리돼 있어 broken image 가 되는 문제를 차단)
    await waitFor(() =>
      expect(mockChain.setImage).toHaveBeenCalledWith({
        src: "http://localhost:8000/static/popup-images/abc.png",
      }),
    );
  });

  it("업로드 실패 시 에러 메시지 노출 + setImage 호출 안 함", async () => {
    const onImageUpload = vi.fn().mockRejectedValue(new Error("용량 초과"));
    render(
      <RichTextEditor
        value=""
        onChange={() => {}}
        onImageUpload={onImageUpload}
      />,
    );

    const file = new File(["x"], "x.png", { type: "image/png" });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("용량 초과"),
    );
    expect(mockChain.setImage).not.toHaveBeenCalled();
  });
});
