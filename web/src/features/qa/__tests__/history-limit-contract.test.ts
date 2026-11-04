/**
 * 이전 대화 턴 수 상한의 **프런트·백엔드 동치** — 3차 검수 P2.
 *
 * 검수 P0-6 결함은 "프런트는 무제한 전송, 서버 스키마는 30 상한" 이어서 31턴째부터
 * 요청이 통째로 422 로 거부되던 것이었다. 지금은 양쪽이 30 이지만, 두 값이 **같은지
 * 확인하는 테스트가 없었다.** 한쪽만 바뀌면 같은 결함이 그대로 재발한다.
 *
 * 프런트에서 파이썬 상수를 import 할 수는 없으므로, 백엔드 소스에서 값을 읽어 비교한다.
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MAX_HISTORY_TURN_IDS } from "@/features/qa/hooks/useQAStream";

// 이 테스트 파일 위치 기준으로 저장소 루트를 거슬러 올라간다
// (vitest 의 cwd 설정에 의존하지 않도록).
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..", "..", "..", "..", "..");
const BACKEND_FILE = join(
  REPO_ROOT,
  "api",
  "src",
  "services",
  "chat_history_service.py",
);

function readBackendConstant(name: string): number {
  let src: string;
  try {
    src = readFileSync(BACKEND_FILE, "utf-8");
  } catch (e) {
    throw new Error(
      `백엔드 소스를 읽지 못했다: ${BACKEND_FILE} (${(e as Error).message})`,
    );
  }
  // String.raw — 템플릿 리터럴에서 `\s` / `\d` 가 그냥 s / d 로 먹히는 것을 막는다.
  const m = new RegExp(String.raw`^${name}\s*=\s*(\d+)`, "m").exec(src);
  expect(m, `${name} 를 백엔드 소스에서 찾지 못했다`).not.toBeNull();
  return Number(m![1]);
}

describe("이전 대화 턴 수 상한 (검수 P0-6 재발 방지)", () => {
  it("프런트 상한이 백엔드 MAX_HISTORY_TURN_IDS 와 같다", () => {
    expect(MAX_HISTORY_TURN_IDS).toBe(readBackendConstant("MAX_HISTORY_TURN_IDS"));
  });

  it("백엔드의 두 상한(요청 스키마용·수신 방어선용)도 서로 같다", () => {
    // 둘이 어긋나면 "스키마는 통과했는데 내부에서 잘린다" 는 조용한 불일치가 생긴다.
    expect(readBackendConstant("MAX_INCOMING_TURNS")).toBe(
      readBackendConstant("MAX_HISTORY_TURN_IDS"),
    );
  });

  it("상한은 1 이상이다", () => {
    expect(MAX_HISTORY_TURN_IDS).toBeGreaterThan(0);
  });
});
