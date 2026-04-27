const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface FeedbackResponse {
  qa_log_id: number;
  rating: "good" | "bad";
  change_count: number;
  action: "created" | "updated" | "unchanged";
}

export async function submitFeedback(
  qaLogId: number,
  rating: "good" | "bad",
): Promise<FeedbackResponse> {
  const res = await fetch(`${API_BASE}/api/v1/qa/feedback`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qa_log_id: qaLogId, rating }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body?.message ?? `feedback submit failed: ${res.status}`);
    (err as { code?: string }).code = body?.code;
    (err as { status?: number }).status = res.status;
    throw err;
  }
  return res.json();
}
