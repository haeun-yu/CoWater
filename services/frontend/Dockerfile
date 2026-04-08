FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:22-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* 변수는 빌드 시점에 번들에 삽입되므로 ARG → ENV로 전달
ARG NEXT_PUBLIC_API_URL=http://localhost:7700
ARG NEXT_PUBLIC_WS_URL=ws://localhost:7700
ARG NEXT_PUBLIC_AGENTS_URL=http://localhost:7701
ARG NEXT_PUBLIC_POSITION_WS_URL=ws://localhost:7703
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_AGENTS_URL=$NEXT_PUBLIC_AGENTS_URL
ENV NEXT_PUBLIC_POSITION_WS_URL=$NEXT_PUBLIC_POSITION_WS_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
