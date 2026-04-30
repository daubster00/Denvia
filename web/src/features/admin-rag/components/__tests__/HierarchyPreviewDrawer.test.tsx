import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { HierarchyPreviewDrawer } from "../HierarchyPreviewDrawer";

const mockHierarchy = [
  { major: "보철", minors: ["크라운", "브릿지", "의치"] },
  { major: "근관치료", minors: ["급성 치수염"] },
];

describe("HierarchyPreviewDrawer", () => {
  it("open=false이면 렌더 없음", () => {
    render(
      <HierarchyPreviewDrawer
        open={false}
        hierarchy={mockHierarchy}
        filename="test.txt"
        chunkCount={10}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("open=true이면 트리 렌더", () => {
    render(
      <HierarchyPreviewDrawer
        open
        hierarchy={mockHierarchy}
        filename="test.txt"
        chunkCount={10}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByText("보철")).toBeDefined();
    // 중분류 아이템은 "├ 크라운" 형태로 렌더 → 부분 매칭
    expect(screen.getByText(/크라운/)).toBeDefined();
    expect(screen.getByText("근관치료")).toBeDefined();
    expect(screen.getByText(/급성 치수염/)).toBeDefined();
  });

  it("파일명·청크수 표시", () => {
    render(
      <HierarchyPreviewDrawer
        open
        hierarchy={mockHierarchy}
        filename="치과지식.txt"
        chunkCount={42}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/치과지식\.txt/)).toBeDefined();
    expect(screen.getByText(/42개 청크/)).toBeDefined();
  });

  it("Esc 키 → onClose 호출", () => {
    const onClose = vi.fn();
    render(
      <HierarchyPreviewDrawer
        open
        hierarchy={mockHierarchy}
        filename="test.txt"
        chunkCount={5}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("오버레이 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    render(
      <HierarchyPreviewDrawer
        open
        hierarchy={mockHierarchy}
        filename="test.txt"
        chunkCount={5}
        onClose={onClose}
      />,
    );
    const overlay = screen.getByTestId("drawer-overlay");
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("[확인] 버튼 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    render(
      <HierarchyPreviewDrawer
        open
        hierarchy={mockHierarchy}
        filename="test.txt"
        chunkCount={5}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "확인" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
