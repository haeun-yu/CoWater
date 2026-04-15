import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  productionBrowserSourceMaps: false,
  webpack: (config) => {
    // maplibre-gl worker 번들링
    config.resolve.alias = {
      ...config.resolve.alias,
      "maplibre-gl": "maplibre-gl",
    };
    return config;
  },
  experimental: {
    optimizePackageImports: ["zustand", "date-fns", "@turf/turf"],
  },
};

export default nextConfig;
