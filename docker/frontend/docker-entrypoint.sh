#!/bin/sh
set -e

# Inyectar variables en config.js
envsubst '${BACKEND_URL} ${ENVIRONMENT} ${APP_VERSION}' < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js

# Inyectar versión en index.html usando sed (más robusto para HTML)
sed "s/\${APP_VERSION}/$APP_VERSION/g" /usr/share/nginx/html/index.template.html > /usr/share/nginx/html/index.html

echo "[Entrypoint] Version $APP_VERSION injected into index.html and config.js"

exec nginx -g "daemon off;"