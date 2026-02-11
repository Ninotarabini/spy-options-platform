FROM nginx:1.25-alpine

RUN apk add --no-cache gettext \
 && rm -rf /etc/nginx/conf.d/*

LABEL maintainer="vicentetarabini@gmail.com"
LABEL description="SPY Options Frontend - Static Dashboard with env injection"

# Install envsubst (part of gettext package)
RUN apk add --no-cache gettext

# Copy static files
COPY index.html /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY config.js /usr/share/nginx/html/
COPY config.template.js /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/nginx.conf
 Entrypoint script for env substitution
RUN echo '#!/bin/sh' > /docker-entrypoint.sh && \
   echo 'set -e' >> /docker-entrypoint.sh && \
   echo 'envsubst < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js' >> /docker-entrypoint.sh && \
   echo 'exec nginx -g "daemon off;"' >> /docker-entrypoint.sh && \
   chmod +x /docker-entrypoint.sh

# Non-root setup
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

# Create nginx temp directories for non-root
RUN mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp && \
    chmod 700 /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp && \
    chown -R nginx:nginx /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp
USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
# CMD ["nginx", "-g", "daemon off;"]
