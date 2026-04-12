FROM oven/bun:1.3.6-alpine AS build

WORKDIR /app
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
