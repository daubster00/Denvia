"use client";

export default function GlobalError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body>
        <h2>치명적인 오류가 발생했습니다.</h2>
        <button onClick={reset}>다시 시도</button>
      </body>
    </html>
  );
}
