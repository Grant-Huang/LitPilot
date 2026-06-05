import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import "@/styles/meso-platform.css";
import { Chrome } from "@/components/layout/Chrome";
import { AntdRegistryProvider } from "./antd-registry";

const geistSans = Geist({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const viewport: Viewport = {
  themeColor: "#0E1633",
};

export const metadata: Metadata = {
  title: "LitPilot — Literature review, on autopilot",
  description: "Literature review, on autopilot.",
  manifest: "/brand/site.webmanifest",
  icons: {
    icon: [
      { url: "/brand/svg/favicon.svg", type: "image/svg+xml" },
      { url: "/brand/png/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/brand/png/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/brand/png/apple-touch-icon-180.png",
  },
  openGraph: {
    title: "LitPilot",
    description: "Literature review, on autopilot.",
    images: [{ url: "/brand/png/og-image-1200x630.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LitPilot",
    description: "Literature review, on autopilot.",
    images: ["/brand/png/og-image-1200x630.png"],
  },
};

const themeInitScript = `(function(){var t=localStorage.getItem('meso-theme')||'light';document.documentElement.setAttribute('data-theme',t);})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="zh"
      className={`${geistSans.variable} ${geistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="meso-theme litpilot-branded" style={{ height: "100vh", overflow: "hidden" }}>
        <Script id="meso-theme-init" strategy="beforeInteractive">
          {themeInitScript}
        </Script>
        <AntdRegistryProvider>
          <Chrome>{children}</Chrome>
        </AntdRegistryProvider>
      </body>
    </html>
  );
}
