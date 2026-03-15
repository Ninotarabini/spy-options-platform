#!/bin/sh
set -e
envsubst '${BACKEND_URL} ${ENVIRONMENT} ${APP_VERSION}' < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js
envsubst '${APP_VERSION}' < /usr/share/nginx/html/index.template.html > /usr/share/nginx/html/index.html
exec nginx -g "daemon off;"