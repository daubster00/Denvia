const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function postClientEvent(
  event: string,
  traceId?: string,
): Promise<void> {
  await fetch(`${API_BASE}/api/v1/events/client`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, trace_id: traceId ?? null }),
  }).catch(() => {
    // fire-and-forget: 실패해도 초기화 UX 미차단
  });
}
