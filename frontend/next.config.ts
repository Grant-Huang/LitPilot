import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@meso.ai/ui"],
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
