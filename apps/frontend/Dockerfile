FROM node:24-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_EMBED_PARENT_ORIGINS=https://benhvientimhanoi.vn,https://www.benhvientimhanoi.vn
ARG VITE_EMERGENCY_HOTLINE=115
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_EMBED_PARENT_ORIGINS=$VITE_EMBED_PARENT_ORIGINS \
    VITE_EMERGENCY_HOTLINE=$VITE_EMERGENCY_HOTLINE

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund && npm cache clean --force

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runner

RUN apk upgrade --no-cache libcrypto3 libssl3

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
