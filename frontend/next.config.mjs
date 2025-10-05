import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const backendEnvPath = path.join(__dirname, "..", "backend", ".env");
dotenv.config({ path: backendEnvPath, override: false });

const rootEnvPath = path.join(__dirname, "..", ".env");
dotenv.config({ path: rootEnvPath, override: false });

const nextConfig = {
  experimental: {
    esmExternals: true,
  },
  outputFileTracingRoot: path.join(__dirname, ".."),
};

export default nextConfig;
