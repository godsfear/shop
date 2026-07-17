# Фронт: сборка Vite -> статика, которую раздаёт Caddy (SPA + reverse-proxy /api).
# Caddy собирается с модулем caddy-dns/cloudflare (DNS-01 за оранжевым облаком).
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm ci
COPY . ./
RUN npm run build

# кастомная сборка Caddy: штатный образ не содержит DNS-провайдеров
FROM caddy:2-builder AS caddybuild
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine
COPY --from=caddybuild /usr/bin/caddy /usr/bin/caddy
# локальный (:80), прод (TLS) и общий сниппет; какой активен — выбирает CADDYFILE
COPY Caddyfile Caddyfile.prod Caddyfile.app /etc/caddy/
COPY --from=build /web/dist /srv
EXPOSE 80 443
