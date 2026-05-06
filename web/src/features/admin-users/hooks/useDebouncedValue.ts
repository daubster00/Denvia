"use client";

import { useEffect, useState } from "react";

/**
 * 입력값을 지정 ms 동안 변화가 없을 때만 업데이트하는 디바운스 hook.
 * 검색 입력처럼 타이핑 중 과도한 fetch를 막을 때 사용한다.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
