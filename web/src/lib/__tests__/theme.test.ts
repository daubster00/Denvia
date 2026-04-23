import { describe, it, expect } from "vitest";
import { denviaTokenOverrides, brandGradient, primarySolid } from "../theme";

describe("denviaTokenOverrides", () => {
  it("primary-normal 바이올렛 CSS 변수를 포함한다", () => {
    expect(denviaTokenOverrides).toContain("--semantic-primary-normal: #8B5CF6");
  });

  it("primary-strong 바이올렛 CSS 변수를 포함한다", () => {
    expect(denviaTokenOverrides).toContain("--semantic-primary-strong: #7C3AED");
  });

  it("primary-heavy 다크 바이올렛 CSS 변수를 포함한다", () => {
    expect(denviaTokenOverrides).toContain("--semantic-primary-heavy: #6D28D9");
  });
});

describe("brandGradient", () => {
  it("바이올렛→핑크 그라디언트 값이 올바르다", () => {
    expect(brandGradient).toContain("#8B5CF6");
    expect(brandGradient).toContain("#D946EF");
  });
});

describe("primarySolid", () => {
  it("그라디언트 대비 미달 시 사용할 solid fallback이 바이올렛이다", () => {
    expect(primarySolid).toBe("#7C3AED");
  });
});
