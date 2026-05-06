import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";

// next/dynamic을 동기 통과시켜 RichTextEditor mock 컴포넌트가 즉시 마운트되도록.
vi.mock("next/dynamic", () => ({
  default: (loader: () => Promise<{ default: unknown } | unknown>) => {
    let Comp: React.ComponentType<{
      value: string;
      onChange: (html: string) => void;
    }> | null = null;
    Promise.resolve(loader()).then((mod: unknown) => {
      const m = mod as { default?: unknown };
      Comp =
        (m.default as React.ComponentType<{
          value: string;
          onChange: (html: string) => void;
        }>) ??
        (mod as React.ComponentType<{
          value: string;
          onChange: (html: string) => void;
        }>);
    });
    return function DynamicMock(props: {
      value: string;
      onChange: (html: string) => void;
    }) {
      // RichTextEditor를 단순 textarea로 치환 — 본문 입력 검증만 확인.
      return (
        <textarea
          aria-label="팝업 본문"
          value={props.value}
          onChange={(e) => props.onChange(e.target.value)}
        />
      );
    };
  },
}));

const mocks = vi.hoisted(() => ({
  fetchPopupDetail: vi.fn(),
  createPopup: vi.fn(),
  updatePopup: vi.fn(),
}));

vi.mock("@/features/admin-content/api/popup", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/admin-content/api/popup")
  >("@/features/admin-content/api/popup");
  return {
    ...actual,
    fetchPopupDetail: mocks.fetchPopupDetail,
    createPopup: mocks.createPopup,
    updatePopup: mocks.updatePopup,
  };
});

import { PopupEditDialog } from "../PopupEditDialog";
import { ApiError } from "@/features/admin-content/api/popup";

function fillValid() {
  fireEvent.change(screen.getByLabelText(/제목/), {
    target: { value: "테스트 팝업" },
  });
  fireEvent.change(screen.getByLabelText("팝업 본문"), {
    target: { value: "<p>안녕</p>" },
  });
  fireEvent.change(screen.getByLabelText(/노출 시작/), {
    target: { value: "2026-05-01T00:00" },
  });
  fireEvent.change(screen.getByLabelText(/노출 종료/), {
    target: { value: "2026-05-31T23:59" },
  });
}

describe("PopupEditDialog", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("작성 모드 — 제목이 비면 인라인 에러", async () => {
    render(
      <PopupEditDialog
        mode="create"
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(
        screen.getByText("제목을 입력해주세요"),
      ).toBeDefined();
    });
    expect(mocks.createPopup).not.toHaveBeenCalled();
  });

  it("종료일 <= 시작일이면 display_end 인라인 에러", async () => {
    render(
      <PopupEditDialog
        mode="create"
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText(/제목/), {
      target: { value: "OK" },
    });
    fireEvent.change(screen.getByLabelText("팝업 본문"), {
      target: { value: "<p>x</p>" },
    });
    fireEvent.change(screen.getByLabelText(/노출 시작/), {
      target: { value: "2026-05-31T23:59" },
    });
    fireEvent.change(screen.getByLabelText(/노출 종료/), {
      target: { value: "2026-05-01T00:00" },
    });
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(
        screen.getByText("종료일은 시작일보다 늦어야 합니다"),
      ).toBeDefined();
    });
    expect(mocks.createPopup).not.toHaveBeenCalled();
  });

  it("link_url이 https가 아니면 인라인 에러", async () => {
    render(
      <PopupEditDialog
        mode="create"
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fillValid();
    fireEvent.change(screen.getByLabelText(/링크 URL/), {
      target: { value: "ftp://example.com" },
    });
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(
        screen.getByText(/https:\/\/ 또는 http:\/\//),
      ).toBeDefined();
    });
  });

  it("정상 입력 → createPopup 호출 + onSaved + onClose", async () => {
    mocks.createPopup.mockResolvedValue({ id: 1 });
    const onSaved = vi.fn();
    const onClose = vi.fn();
    render(
      <PopupEditDialog
        mode="create"
        onClose={onClose}
        onSaved={onSaved}
      />,
    );
    fillValid();
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(mocks.createPopup).toHaveBeenCalledTimes(1);
    });
    expect(onSaved).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("백엔드 422 POPUP_DISPLAY_RANGE_INVALID → display_end 필드 에러 매핑", async () => {
    mocks.createPopup.mockRejectedValue(
      new ApiError("종료일은 시작일보다 늦어야 합니다.", 422, "POPUP_DISPLAY_RANGE_INVALID"),
    );
    render(
      <PopupEditDialog
        mode="create"
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fillValid();
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(
        screen.getByText("종료일은 시작일보다 늦어야 합니다."),
      ).toBeDefined();
    });
  });

  it("백엔드 422 POPUP_LINK_URL_INVALID → link_url 필드 에러 매핑", async () => {
    mocks.createPopup.mockRejectedValue(
      new ApiError(
        "http:// 또는 https://로 시작하는 URL을 입력해주세요.",
        422,
        "POPUP_LINK_URL_INVALID",
      ),
    );
    render(
      <PopupEditDialog
        mode="create"
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fillValid();
    fireEvent.change(screen.getByLabelText(/링크 URL/), {
      target: { value: "https://example.com" },
    });
    fireEvent.click(screen.getByText("저장"));
    await waitFor(() => {
      expect(
        screen.getAllByText(/http:\/\/ 또는 https:\/\//).length,
      ).toBeGreaterThan(0);
    });
  });

  it("편집 모드 — fetchPopupDetail 호출 + form prefill", async () => {
    mocks.fetchPopupDetail.mockResolvedValue({
      id: 42,
      title: "기존 팝업",
      body_html: "<p>본문</p>",
      link_url: "https://example.com",
      display_start: "2026-05-01T00:00:00+00:00",
      display_end: "2026-05-31T00:00:00+00:00",
      target_segment: "doctor",
      is_active: true,
      created_by_admin_id: 1,
      created_at: "2026-04-30T00:00:00+00:00",
      updated_at: "2026-04-30T00:00:00+00:00",
    });
    render(
      <PopupEditDialog
        mode="edit"
        popupId={42}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    await waitFor(() => {
      expect(
        (screen.getByLabelText(/제목/) as HTMLInputElement).value,
      ).toBe("기존 팝업");
    });
    expect(mocks.fetchPopupDetail).toHaveBeenCalledWith(42);
  });

  it("취소 버튼 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    render(
      <PopupEditDialog
        mode="create"
        onClose={onClose}
        onSaved={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("취소"));
    expect(onClose).toHaveBeenCalled();
  });
});
