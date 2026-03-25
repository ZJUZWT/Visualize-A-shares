FROM node:20-slim AS deps

WORKDIR /app/frontend

COPY package.json package-lock.json ./
RUN npm ci


FROM node:20-slim AS builder

WORKDIR /app/frontend

ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}

COPY --from=deps /app/frontend/node_modules ./node_modules
COPY . .
RUN npm run build


FROM node:20-slim AS runtime

WORKDIR /app/frontend

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/frontend/package.json ./package.json
COPY --from=builder /app/frontend/package-lock.json ./package-lock.json
COPY --from=builder /app/frontend/node_modules ./node_modules
COPY --from=builder /app/frontend/.next ./.next
COPY --from=builder /app/frontend/public ./public
COPY --from=builder /app/frontend/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
