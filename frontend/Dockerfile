# syntax=docker/dockerfile:1.6
# Build stage — Node compiles the Vite SPA into static assets.
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

RUN npm run build

# Runtime stage — nginx serves the built static files and proxies /api to the
# backend service. Keeping nginx (not `vite preview`) so the production server
# isn't dev-mode and the container stays minimal.
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
