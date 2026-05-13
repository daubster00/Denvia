"use client";

/** 고객문의 제출 mutation — 0030 1:1 문의 게시판화. */

import { useMutation } from "@tanstack/react-query";

import {
  type InquirySubmitArgs,
  type InquirySubmitResponse,
  postInquiry,
} from "../api";

export function useSubmitInquiry() {
  return useMutation<InquirySubmitResponse, Error, InquirySubmitArgs>({
    mutationFn: (args) => postInquiry(args),
  });
}
