import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 开发时把 /api 代理到本地后端，前端代码只使用相对路径。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "DMS_");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.DMS_API_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
