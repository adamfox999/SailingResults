import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  outputFileTracingRoot: path.join(__dirname, ".."),
  // Skip static generation for error pages
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb'
    },
    // This prevents prerendering of special error pages during build
    optimizeServerReact: false,
  },
};

export default nextConfig;
