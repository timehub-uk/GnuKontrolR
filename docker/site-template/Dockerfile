# ────────────────────────────────────────────────────────────────────────────
# WebPanel Customer Site Container
# Base image: webpanel/php-site:8.2
#
# Pre-installed services (all optional via supervisor):
#   - PHP-FPM 8.2            (always on)
#   - Nginx                  (default web server)
#   - Apache2                (optional)
#   - Lighttpd               (optional)
#   - Node.js 20 + PM2       (optional)
#   - SQLite3                (customer local DB)
#   - Composer               (PHP deps)
#   - WP-CLI                 (WordPress management)
#
# Environment variables injected at runtime:
#   DOMAIN          — domain name
#   DB_HOST         — mysql-master hostname  (webpanel_mysql)
#   DB_NAME         — customer database name
#   DB_USER         — customer DB user
#   DB_PASS         — customer DB password
#   REDIS_URL       — redis://... shared cache
#   SMTP_HOST       — outbound mail relay
#   WEB_SERVER      — nginx|apache|lighthttpd  (default: nginx)
#   NODE_APP        — path to Node.js entry point (optional)
# ────────────────────────────────────────────────────────────────────────────

FROM php:8.2-fpm-bookworm

LABEL maintainer="WebPanel"
LABEL description="Customer site container with multi-server support"

# System deps + all optional web servers in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx apache2 lighttpd supervisor curl wget unzip git openssh-server \
        sqlite3 libsqlite3-dev libmysqlclient-dev default-libmysqlclient-dev \
        libpng-dev libjpeg-dev libwebp-dev libfreetype6-dev \
        libxml2-dev libzip-dev libonig-dev libcurl4-openssl-dev \
        libssl-dev libicu-dev gnupg2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 via NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pm2 \
    && rm -rf /var/lib/apt/lists/*

# PHP extensions
RUN docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j$(nproc) \
        gd pdo pdo_mysql mysqli zip intl opcache mbstring curl bcmath xml

# Composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

# WP-CLI
RUN curl -O https://raw.githubusercontent.com/wp-cli/wp-cli/main/utils/wp-completion.bash \
    && curl -L https://github.com/wp-cli/wp-cli/releases/download/v2.9.0/wp-cli-2.9.0.phar \
       -o /usr/local/bin/wp && chmod +x /usr/local/bin/wp 2>/dev/null || true

# Copy config templates
COPY conf/nginx.conf      /etc/nginx/sites-available/default
COPY conf/apache.conf     /etc/apache2/sites-available/000-default.conf
COPY conf/lighttpd.conf   /etc/lighttpd/lighttpd.conf
COPY conf/php-fpm.conf    /usr/local/etc/php-fpm.d/www.conf
COPY conf/supervisord.conf /etc/supervisor/conf.d/webpanel.conf
COPY conf/opcache.ini     /usr/local/etc/php/conf.d/opcache.ini
COPY conf/sshd_config     /etc/ssh/sshd_config

# ── GnuKontrolR system user ──────────────────────────────────────────────────
# gnukontrolr-admin: internal system account that manages secure configs and
# services. Full service-management rights but NOT root. No login shell, no SSH.
# Customer (www-data) has zero access to files owned by this user.
RUN groupadd -r gnukontrolr \
    && useradd -r -g gnukontrolr -s /sbin/nologin -d /var/gnukontrolr -M gnukontrolr-admin \
    && mkdir -p /var/gnukontrolr \
    && chown gnukontrolr-admin:gnukontrolr /var/gnukontrolr \
    && chmod 750 /var/gnukontrolr \
    # Allow gnukontrolr-admin to control services (supervisorctl) without root
    && echo 'gnukontrolr-admin ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl, /usr/sbin/nginx, /usr/sbin/apache2ctl, /usr/sbin/lighttpd' \
       > /etc/sudoers.d/gnukontrolr-admin \
    && chmod 440 /etc/sudoers.d/gnukontrolr-admin \
    # webpanel-sys: used by the main panel host service to write configs
    && useradd -r -g gnukontrolr -s /sbin/nologin -d /nonexistent -M webpanel-sys \
    && echo 'webpanel-sys ALL=(gnukontrolr-admin) NOPASSWD: ALL' \
       > /etc/sudoers.d/webpanel-sys \
    && chmod 440 /etc/sudoers.d/webpanel-sys

# Install Flask for container API
RUN pip3 install flask --break-system-packages 2>/dev/null || pip3 install flask

# Copy container API
COPY container_api.py /container_api.py

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── Container directory layout ────────────────────────────────────────────────
# /var/www/html          Public web root (customer edits freely)
# /var/customer/uploads  Customer uploads (private, not web-accessible)
# /var/customer/private  Private data storage
# /var/customer/backups  Customer backups
# /var/config            Secure area — system configs managed via API only
# /var/config/nginx      Nginx site config
# /var/config/php        PHP config overrides
# /var/config/env        Environment / secrets (owned by root, readable by api)
# /var/config/ssl        Customer SSL certs
# /var/db                SQLite and SSH keys
RUN mkdir -p \
        /var/www/html \
        /var/customer/uploads \
        /var/customer/private \
        /var/customer/backups \
        /var/config/nginx \
        /var/config/php \
        /var/config/env \
        /var/config/ssl \
        /var/log/supervisor \
        /var/db \
    && chown -R www-data:www-data /var/www/html /var/customer \
    && chmod 750 /var/config \
    && chmod 700 /var/config/env

# Nginx include for customer config overrides
RUN echo 'include /var/config/nginx/*.conf;' >> /etc/nginx/sites-available/default 2>/dev/null || true

# Default index
RUN echo '<?php echo "<h1>Welcome to your hosting space</h1><p>Upload your files to get started.</p>";' \
    > /var/www/html/index.php \
    && chown www-data:www-data /var/www/html/index.php

VOLUME ["/var/www/html", "/var/customer", "/var/db"]

EXPOSE 80 443 3000 9000 22

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/webpanel.conf"]
