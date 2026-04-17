import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output produces a self-contained server.js + slim node_modules,
  // copied into the production Docker image (docker/Dockerfile.frontend).
  // Without this, the runtime stage would need the full pnpm install.
  output: "standalone",
};

export default nextConfig;
