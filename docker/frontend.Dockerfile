# 前端：React + Vite 开发服务器，/api 代理到 backend 容器。
FROM node:20-slim

# 国内网络可传入：--build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry "$NPM_REGISTRY"
COPY frontend/ ./

ENV DMS_API_TARGET=http://backend:8000
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
