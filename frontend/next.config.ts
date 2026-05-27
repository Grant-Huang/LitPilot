import type { NextConfig } from "next";

const backendBase =
  process.env.BACKEND_URL ||
  process.env.API_PROXY_TARGET ||
  "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  transpilePackages: ["@meso.ai/ui"],
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
