# Общие директивы (импортируются и локальным, и прод-конфигом): SPA + /api.
encode gzip zstd

# API -> бэкенд по имени сервиса в compose-сети. Caddy резолвит upstream сам
# при каждом соединении: пересоздание контейнера api не даёт 502 (в nginx для
# этого нужен был resolver + переменная).
handle /api/* {
	reverse_proxy api:8000
}

# хешированные ассеты Vite неизменны -> кэш на год
handle /assets/* {
	root * /srv
	header Cache-Control "public, max-age=31536000, immutable"
	file_server
}

# SPA-маршруты (/episode/:id, /profile, ...) -> index.html; no-cache, чтобы после
# деплоя не висел старый бандл (ассеты кэшируются выше)
handle {
	root * /srv
	header Cache-Control "no-cache"
	try_files {path} /index.html
	file_server
}

# загрузка документов/анализов — как было в nginx (client_max_body_size 60m)
request_body {
	max_size 60MB
}
