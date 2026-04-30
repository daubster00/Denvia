"use client";

/** 고객문의 제출 mutation — Story 4.5. */

import { useMutation } from "@tanstack/react-query";

import { postInquiry } from "../api";

interface SubmitArgs {
  subject: string;
  body: string;
}

interface SubmitResult {
  inquiry_id: number;
}

export function useSubmitInquiry() {
  return useMutation<SubmitResult, Error, SubmitArgs>({
    mutationFn: ({ subject, body }) => postInquiry(subject, body),
  });
}
