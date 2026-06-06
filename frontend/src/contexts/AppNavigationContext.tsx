"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useTransition,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

type AppNavigationContextValue = {
  pendingHref: string | null;
  navigate: (href: string) => void;
  isNavigating: boolean;
};

const AppNavigationContext = createContext<AppNavigationContextValue | null>(null);

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
  const [isNavigating, startTransition] = useTransition();

  useEffect(() => {
    setPendingHref(null);
  }, [pathname]);

  const navigate = useCallback(
    (href: string) => {
      if (!href || href === pathname) return;
      setPendingHref(href);
      startTransition(() => {
        router.push(href);
      });
    },
    [pathname, router],
  );

  const value = useMemo(
    () => ({
      pendingHref,
      navigate,
      isNavigating,
    }),
    [pendingHref, navigate, isNavigating],
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
