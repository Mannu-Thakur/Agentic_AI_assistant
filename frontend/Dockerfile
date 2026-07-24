# ─────────────────────────────────────────────────────────────────────────────
#  Build stage: install deps and build the Vite/React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests first for layer caching
COPY package.json package-lock.json* ./

RUN npm ci --silent

# Copy the rest of the source
COPY . .

# Build production bundle
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
#  Production stage: serve the built bundle with nginx
# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Remove default nginx config and replace with ours
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built bundle from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Health check: nginx responds on port 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
