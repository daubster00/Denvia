import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModelParamForm } from "../ModelParamForm";

vi.mock("../../api/prompts", () => ({
  updateModelParams: vi.fn(),
  modelParamsSchema: {
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

const defaultParams = {
  rag_k: 5,
  rag_temperature: 0.0,
  max_tokens: 1024,
};

describe("ModelParamForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("초기 렌더: defaults 값으로 필드 채워짐", () => {
    renderWithQuery(<ModelParamForm defaults={defaultParams} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const values = inputs.map((i) => Number(i.value));

    expect(values).toContain(5);    // rag_k
    expect(values).toContain(0);    // rag_temperature
    expect(values).toContain(1024); // max_tokens
  });

  it("정상 입력 후 [저장] 클릭 → ConfirmDialog 오픈", async () => {
    renderWithQuery(<ModelParamForm defaults={defaultParams} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: "8" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(
        screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?")
      ).toBeDefined();
    });
  });

  it("ConfirmDialog 확인 → updateModelParams 호출", async () => {
    const { updateModelParams } = await import("../../api/prompts");
    (updateModelParams as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);

    renderWithQuery(<ModelParamForm defaults={defaultParams} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: "8" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?");
    });

    const confirmBtns = screen.getAllByText("저장");
    fireEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => {
      expect(updateModelParams).toHaveBeenCalled();
    });
  });

  it("ConfirmDialog 취소 → updateModelParams 호출 없음", async () => {
    const { updateModelParams } = await import("../../api/prompts");

    renderWithQuery(<ModelParamForm defaults={defaultParams} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: "8" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?");
    });

    // ConfirmDialog의 취소 버튼 (폼 취소 버튼과 구분)
    const cancelBtns = screen.getAllByText("취소");
    fireEvent.click(cancelBtns[cancelBtns.length - 1]);

    expect(updateModelParams).not.toHaveBeenCalled();
  });

  it("[취소] 버튼 클릭 → defaults 값으로 reset", () => {
    renderWithQuery(<ModelParamForm defaults={defaultParams} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: "15" } });

    const cancelBtn = screen.getByText("취소");
    fireEvent.click(cancelBtn);

    const resetInputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    expect(Number(resetInputs[0].value)).toBe(5);
  });

  it("성공 후 queryClient.invalidateQueries 호출 — admin-rag-model-params", async () => {
    const { updateModelParams } = await import("../../api/prompts");
    (updateModelParams as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    render(
      <QueryClientProvider client={client}>
        <ModelParamForm defaults={defaultParams} />
      </QueryClientProvider>
    );

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: "8" } });

    const saveBtn = screen.getByText("저장");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      screen.getByText("저장 시 모든 신규 쿼리에 즉시 반영됩니다. 진행하시겠습니까?");
    });

    const confirmBtns = screen.getAllByText("저장");
    fireEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["admin-rag-model-params"] })
      );
    });
  });
});
