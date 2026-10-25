import type { NextConfig } from "next";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/requests/:path*", destination: "http://127.0.0.1:8000/requests/:path*" }];
  },
};

export default config;
