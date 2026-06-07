"use client";

import Link from "next/link";
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

/** Routes reached from the app shell sidebar / user menu. */
export const APP_SHELL_ROUTES = [
  "/chat",
  "/library",
  "/settings/personal",
  "/settings/admin",
] as const;

type AppNavigationContextValue = {
  pendingHref: string | null;
  navigate: (href: string) => void;
  isNavigating: boolean;
};

const AppNavigationContext = createContext<AppNavigationContextValue | null>(null);

const NAV_PENDING_TIMEOUT_MS = 15_000;
/** Soft navigation can stall without prefetch; hard-nav if URL unchanged. */
const NAV_HARD_FALLBACK_MS = 450;

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
  const linkRefs = useRef(new Map<string, HTMLAnchorElement>());
  const pendingTimerRef = useRef<number | null>(null);
  const fallbackTimerRef = useRef<number | null>(null);

  useEffect(() => {
    for (const href of APP_SHELL_ROUTES) {
      void router.prefetch(href);
    }
  }, [router]);

  useEffect(() => {
    setPendingHref(null);
    if (pendingTimerRef.current !== null) {
      window.clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
    if (fallbackTimerRef.current !== null) {
      window.clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, [pathname]);

  useEffect(() => {
    return () => {
      if (pendingTimerRef.current !== null) {
        window.clearTimeout(pendingTimerRef.current);
      }
      if (fallbackTimerRef.current !== null) {
        window.clearTimeout(fallbackTimerRef.current);
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

      void router.prefetch(href);

      const anchor = linkRefs.current.get(href);
      if (anchor) {
        anchor.click();
      } else {
        router.push(href);
      }

      if (fallbackTimerRef.current !== null) {
        window.clearTimeout(fallbackTimerRef.current);
      }
      fallbackTimerRef.current = window.setTimeout(() => {
        fallbackTimerRef.current = null;
        if (window.location.pathname !== href) {
          window.location.assign(href);
        }
      }, NAV_HARD_FALLBACK_MS);
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
    <AppNavigationContext.Provider value={value}>
      <div className="litpilot-app-nav__prefetch" aria-hidden>
        {APP_SHELL_ROUTES.map((href) => (
          <Link
            key={href}
            href={href}
            prefetch
            tabIndex={-1}
            ref={(el) => {
              if (el) linkRefs.current.set(href, el);
              else linkRefs.current.delete(href);
            }}
          >
            {href}
          </Link>
        ))}
      </div>
      {children}
    </AppNavigationContext.Provider>
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
