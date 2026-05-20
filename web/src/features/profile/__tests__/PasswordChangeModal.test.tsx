/** 비밀번호 변경 모달 — 2단계 흐름 단위 테스트 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { PasswordChangeModal } from "../PasswordChangeModal";
import { useToastStore } from "@/stores/toast-store";
import { ApiError } from "@/types/api";
import * as profileApi from "../api";

function renderModal(open = true) {
  const onClose = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <PasswordChangeModal open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

beforeEach(() => {
  useToastStore.setState({ current: null });
  vi.restoreAllMocks();
});

describe("PasswordChangeModal", () => {
  it("초기 단계는 '기존 비밀번호 확인'", () => {
    renderModal();
    expect(screen.getByRole("heading", { name: /기존 비밀번호 확인/ })).toBeDefined();
  });

  it("기존 PW 입력 후 '다음' → 새 비밀번호 단계로 전환", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(screen.getByLabelText(/현재 비밀번호/), "oldpw1234");
    await user.click(screen.getByRole("button", { name: /^다음$/ }));
    expect(
      screen.getByRole("heading", { name: /새 비밀번호 등록/ }),
    ).toBeDefined();
    expect(screen.getByLabelText(/^새 비밀번호$/)).toBeDefined();
    expect(screen.getByLabelText(/새 비밀번호 확인/)).toBeDefined();
  });

  it("새 PW와 확인이 다르면 인라인 에러", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(screen.getByLabelText(/현재 비밀번호/), "oldpw1234");
    await user.click(screen.getByRole("button", { name: /^다음$/ }));
    await user.type(screen.getByLabelText(/^새 비밀번호$/), "newpw1234");
    await user.type(screen.getByLabelText(/새 비밀번호 확인/), "different5");
    await user.click(screen.getByRole("button", { name: /^변경$/ }));
    expect(screen.getByRole("alert").textContent).toContain("일치하지 않");
  });

  it("성공 시 API 호출 + Toast + onClose", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn(profileApi, "changePasswordWithCurrent")
      .mockResolvedValue();
    const { onClose } = renderModal();

    await user.type(screen.getByLabelText(/현재 비밀번호/), "oldpw1234");
    await user.click(screen.getByRole("button", { name: /^다음$/ }));
    await user.type(screen.getByLabelText(/^새 비밀번호$/), "newpw1234");
    await user.type(screen.getByLabelText(/새 비밀번호 확인/), "newpw1234");
    await user.click(screen.getByRole("button", { name: /^변경$/ }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({
        current_password: "oldpw1234",
        new_password: "newpw1234",
      });
    });
    expect(onClose).toHaveBeenCalled();
    expect(useToastStore.getState().current?.message).toContain("변경");
  });

  it("AUTH_INVALID_CREDENTIALS → 1단계로 되돌리고 인라인 에러", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "changePasswordWithCurrent").mockRejectedValue(
      new ApiError({
        code: "AUTH_INVALID_CREDENTIALS",
        message: "비밀번호가 일치하지 않습니다",
        trace_id: "",
      }),
    );

    renderModal();
    await user.type(screen.getByLabelText(/현재 비밀번호/), "wrongpw");
    await user.click(screen.getByRole("button", { name: /^다음$/ }));
    await user.type(screen.getByLabelText(/^새 비밀번호$/), "newpw1234");
    await user.type(screen.getByLabelText(/새 비밀번호 확인/), "newpw1234");
    await user.click(screen.getByRole("button", { name: /^변경$/ }));

    await waitFor(() => {
      // 1단계 헤딩으로 복귀
      expect(
        screen.getByRole("heading", { name: /기존 비밀번호 확인/ }),
      ).toBeDefined();
    });
    expect(screen.getByRole("alert").textContent).toContain("일치하지 않");
  });
});
