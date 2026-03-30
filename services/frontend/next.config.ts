import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  webpack: (config) => {
    // maplibre-gl worker 번들링
    config.resolve.alias = {
      ...config.resolve.alias,
      "maplibre-gl": "maplibre-gl",
    };
    return config;
  },
};

export default nextConfig;
