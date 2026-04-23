"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, Global } from "@wanteddev/wds";
import "@wanteddev/wds/global.css";
import { SessionBootstrap } from "@/features/auth/SessionBootstrap";
import { LoginPopupMount } from "@/features/auth/LoginPopupMount";
import { denviaTokenOverrides } from "@/lib/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {/* Denvia 브랜드 토큰 오버라이드 — WDS primary를 바이올렛으로 교체 */}
        <Global styles={denviaTokenOverrides} />
        <SessionBootstrap>
          {children}
          <LoginPopupMount />
        </SessionBootstrap>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
