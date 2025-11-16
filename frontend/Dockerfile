## Multi-stage build for Vite + React (production)
## Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
# Support both presence and absence of package-lock.json
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Pass build-time API base URL (optional). Example:
# docker build --build-arg VITE_APP_API_BASE_URL=http://localhost:8060 -t travelplanner-frontend .
ARG VITE_APP_API_BASE_URL
ENV VITE_APP_API_BASE_URL=${VITE_APP_API_BASE_URL}

# Copy the rest of the source and build
COPY . .
RUN npm run build

## Runtime stage
FROM nginx:alpine AS runtime

# Remove default config and add our SPA-friendly config
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Optional healthcheck (expects 200 from root)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]


