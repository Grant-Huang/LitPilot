"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

type AppNavigationContextValue = {
  pendingHref: string | null;
  navigate: (href: string) => void;
  /** True while a client navigation is in flight (pendingHref set). */
  isNavigating: boolean;
};

const AppNavigationContext = createContext<AppNavigationContextValue | null>(null);

const NAV_PENDING_TIMEOUT_MS = 15_000;

function pendingLabel(label: string, pending: boolean): string {
  return pending ? `${label} …` : label;
}

export function pendingNavLabel(
  href: string,
  label: string,
  pendingHref: string | null,
): string {
  return pendingLabel(label, pendingHref === href);
}

export function AppNavigationProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const pendingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setPendingHref(null);
    if (pendingTimerRef.current !== null) {
      window.clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
  }, [pathname]);

  useEffect(() => {
    return () => {
      if (pendingTimerRef.current !== null) {
        window.clearTimeout(pendingTimerRef.current);
      }
    };
  }, []);

  const navigate = useCallback(
    (href: string) => {
      if (!href || href === pathname) return;
      setPendingHref(href);
      if (pendingTimerRef.current !== null) {
        window.clearTimeout(pendingTimerRef.current);
      }
      pendingTimerRef.current = window.setTimeout(() => {
        setPendingHref((cur) => (cur === href ? null : cur));
        pendingTimerRef.current = null;
      }, NAV_PENDING_TIMEOUT_MS);
      // User-initiated route changes must not use startTransition: chat SSE
      // keeps scheduling urgent updates and can starve low-priority transitions.
      router.push(href);
    },
    [pathname, router],
  );

  const value = useMemo(
    () => ({
      pendingHref,
      navigate,
      isNavigating: pendingHref !== null,
    }),
    [pendingHref, navigate],
  );

  return (
    <AppNavigationContext.Provider value={value}>{children}</AppNavigationContext.Provider>
  );
}

export function useAppNavigation() {
  const ctx = useContext(AppNavigationContext);
  if (!ctx) {
    throw new Error("AppNavigationProvider required");
  }
  return ctx;
}

export function useAppNavigationOptional() {
  return useContext(AppNavigationContext);
}
