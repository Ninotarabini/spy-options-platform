FROM nginx:1.25-alpine

ARG BUILD_VERSION="dev-local"
ENV APP_VERSION=${BUILD_VERSION}

LABEL maintainer="vicentetarabini@gmail.com"
LABEL description="SPY Options Frontend - Static Dashboard with env injection"

# Install envsubst (gettext)
RUN apk add --no-cache gettext \
    && rm -rf /etc/nginx/conf.d/*

# Copy static files
COPY index.html /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY config.template.js /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/nginx.conf

# Entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Permissions
RUN chown -R nginx:nginx /usr/share/nginx/html

# Temp dirs for non-root nginx
RUN mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp \
    && chown -R nginx:nginx /tmp

USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]