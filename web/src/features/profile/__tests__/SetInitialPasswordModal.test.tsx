/** 초기 비밀번호 설정 모달 — 소셜 회원용 1단계 흐름 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SetInitialPasswordModal } from "../SetInitialPasswordModal";
import { useToastStore } from "@/stores/toast-store";
import * as profileApi from "../api";

function renderModal(open = true) {
  const onClose = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <SetInitialPasswordModal open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

beforeEach(() => {
  useToastStore.setState({ current: null });
  vi.restoreAllMocks();
});

describe("SetInitialPasswordModal", () => {
  it("open=false면 렌더되지 않음", () => {
    renderModal(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("8자 미만이면 인라인 에러", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(screen.getByLabelText(/^새 비밀번호$/), "short");
    await user.type(screen.getByLabelText(/비밀번호 확인/), "short");
    await user.click(screen.getByRole("button", { name: /^등록$/ }));
    expect(screen.getByRole("alert").textContent).toContain("8자 이상");
  });

  it("비밀번호와 확인이 다르면 인라인 에러", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(screen.getByLabelText(/^새 비밀번호$/), "newpw1234");
    await user.type(screen.getByLabelText(/비밀번호 확인/), "different9");
    await user.click(screen.getByRole("button", { name: /^등록$/ }));
    expect(screen.getByRole("alert").textContent).toContain("일치하지 않");
  });

  it("성공 시 setInitialPassword 호출 + Toast + onClose", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(profileApi, "setInitialPassword").mockResolvedValue();
    const { onClose } = renderModal();

    await user.type(screen.getByLabelText(/^새 비밀번호$/), "newpw1234");
    await user.type(screen.getByLabelText(/비밀번호 확인/), "newpw1234");
    await user.click(screen.getByRole("button", { name: /^등록$/ }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("newpw1234");
    });
    expect(onClose).toHaveBeenCalled();
    expect(useToastStore.getState().current?.message).toContain("설정");
  });
});
