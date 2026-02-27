#!/bin/sh
set -e
envsubst '${BACKEND_URL} ${ENVIRONMENT} ${APP_VERSION}' < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js
exec nginx -g "daemon off;"