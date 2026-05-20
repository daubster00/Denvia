"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchProfile, type ProfileResponse } from "../api";

export function useProfile() {
  return useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: fetchProfile,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
