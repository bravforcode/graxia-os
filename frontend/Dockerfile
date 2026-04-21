FROM oven/bun:1.3.6-alpine AS build

WORKDIR /app
ARG VITE_API_BASE_URL
ARG VITE_AGENT_STREAM_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AGENT_STREAM_URL=$VITE_AGENT_STREAM_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun run build

FROM nginx:1.27-alpine

RUN addgroup -g 1001 app \
    && adduser -D -u 1001 -G app app \
    && mkdir -p /tmp/nginx/client_temp /tmp/nginx/proxy_temp /tmp/nginx/fastcgi_temp \
    && chown -R app:app /tmp/nginx /var/cache/nginx /var/run /usr/share/nginx/html

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=app:app /app/dist /usr/share/nginx/html

USER 1001:1001
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
