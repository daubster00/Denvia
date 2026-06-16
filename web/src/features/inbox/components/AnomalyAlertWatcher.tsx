"use client";

/** 이상탐지 쪽지 도착 경고 팝업 워처 — #106 (2026-06-16).
 *
 * 범위(사용자 축소 지시): 실시간 폴링/웹소켓 없음. 페이지 전환 시점에 쪽지함 미리보기가
 * 다시 조회되며(useInboxPreview), 그때 새로 도착한 이상탐지(system) 쪽지가 있으면
 * 경고 팝업으로 1회 노출한다.
 *
 * 게이팅:
 * - 무료 플랜(subscription_status === "free") 사용자에게만 노출. pro 에게는 노출 X.
 * - 같은 message_id 는 이 탭 세션에서 1회만 팝업(sessionStorage 로 표시 기록) — 페이지를
 *   여러 번 이동해도 같은 쪽지로 반복 팝업되지 않는다.
 *
 * 데이터 출처는 useInboxPreview(쪽지함 미리보기). 미리보기는 제목만 주므로 팝업 본문에는
 * 제목 + 표준 안내문구를 노출하고, 상세는 쪽지함에서 보도록 유도한다.
 */

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { useSessionStore } from "@/stores/session-store";
import { useAlertStore } from "@/stores/alert-store";
import { useInboxPreview } from "../hooks/useInboxPreview";

const SEEN_KEY = "anomaly_popup_seen_ids";

function readSeenIds(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = sessionStorage.getItem(SEEN_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((v): v is number => typeof v === "number"));
  } catch {
    return new Set();
  }
}

function markSeen(id: number): void {
  if (typeof window === "undefined") return;
  const seen = readSeenIds();
  seen.add(id);
  try {
    sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seen]));
  } catch {
    /* sessionStorage 불가 환경은 무시(팝업이 한 번 더 떠도 무해) */
  }
}

export function AnomalyAlertWatcher() {
  const user = useSessionStore((s) => s.user);
  const show = useAlertStore((s) => s.show);
  const router = useRouter();
  const { data } = useInboxPreview();

  // 같은 렌더 사이클에서 중복 트리거 방지용 가드.
  const lastShownRef = useRef<number | null>(null);

  const isFree = user?.subscription_status === "free";

  useEffect(() => {
    if (!isFree) return;
    if (!data) return;

    // 미읽음 + 이상탐지(system) 쪽지 중, 아직 팝업으로 보여주지 않은 가장 최근 1건.
    const seen = readSeenIds();
    const candidate = data.items.find(
      (it) =>
        it.type === "system" &&
        !it.is_read &&
        !seen.has(it.message_id) &&
        lastShownRef.current !== it.message_id,
    );
    if (!candidate) return;

    lastShownRef.current = candidate.message_id;
    markSeen(candidate.message_id);

    show({
      level: "warning",
      title: candidate.title,
      description:
        "이상로그가 탐지되어 새 쪽지가 도착했습니다.\n자세한 내용은 쪽지함에서 확인해 주세요.",
      dedupeKey: `anomaly-${candidate.message_id}`,
      actions: [
        {
          label: "쪽지함 열기",
          variant: "normal",
          onClick: () => router.push(`/inbox?focus=${candidate.message_id}`),
        },
        { label: "닫기", variant: "assistive" },
      ],
    });
  }, [isFree, data, show, router]);

  return null;
}
