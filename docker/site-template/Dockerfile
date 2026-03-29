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

ARG PHP_VERSION=8.2
FROM php:${PHP_VERSION}-fpm-bookworm

ARG PHP_VERSION=8.2
LABEL maintainer="WebPanel"
LABEL description="Customer site container with multi-server support (PHP ${PHP_VERSION})"

# System deps + all optional web servers in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx apache2 lighttpd supervisor curl wget unzip git openssh-server \
        sqlite3 libsqlite3-dev libmariadb-dev default-libmysqlclient-dev \
        mariadb-server mariadb-client \
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
# Override zz-docker.conf so PHP-FPM uses unix socket (not port 9000, which is reserved for container API)
RUN echo '[www]\nlisten = /var/run/php/php-fpm.sock' > /usr/local/etc/php-fpm.d/zz-docker.conf

# ── GnuKontrolR system user ──────────────────────────────────────────────────
# gnukontrolr-admin: internal system account that manages secure configs and
# services. Full service-management rights but NOT root. SSH access is optional —
# superadmin can inject a public key at runtime via the container API.
# Customer (www-data) has zero access to files owned by this user.
RUN apt-get update && apt-get install -y --no-install-recommends sudo \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r gnukontrolr \
    && useradd -m -g gnukontrolr -s /bin/bash -d /home/gnukontrolr-admin gnukontrolr-admin \
    && usermod -p '*' gnukontrolr-admin \
    && mkdir -p /home/gnukontrolr-admin/.ssh /etc/sudoers.d \
    && chown -R gnukontrolr-admin:gnukontrolr /home/gnukontrolr-admin \
    && chmod 700 /home/gnukontrolr-admin \
    && chmod 700 /home/gnukontrolr-admin/.ssh \
    # Allow gnukontrolr-admin to control services (supervisorctl) without root
    && echo 'gnukontrolr-admin ALL=(ALL) NOPASSWD: /usr/bin/supervisorctl, /usr/sbin/nginx, /usr/sbin/apache2ctl, /usr/sbin/lighttpd' \
       > /etc/sudoers.d/gnukontrolr-admin \
    && chmod 440 /etc/sudoers.d/gnukontrolr-admin \
    # webpanel-sys: used by the main panel host service to write configs
    && useradd -r -g gnukontrolr -s /sbin/nologin -d /nonexistent -M webpanel-sys \
    && echo 'webpanel-sys ALL=(gnukontrolr-admin) NOPASSWD: ALL' \
       > /etc/sudoers.d/webpanel-sys \
    && chmod 440 /etc/sudoers.d/webpanel-sys \
    # webuser: domain customer SSH user — real bash shell, owns web content, no admin rights
    # Uses UID 1001 to be consistent across all site containers (helps with bind-mount permissions)
    && useradd -m -u 1001 -s /bin/bash -d /home/webuser webuser \
    && usermod -p '*' webuser \
    && mkdir -p /home/webuser/.ssh \
    && chmod 700 /home/webuser /home/webuser/.ssh \
    && chown -R webuser:webuser /home/webuser \
    # webuser can run PHP tools, composer, wp-cli, npm as themselves — no password needed
    && echo 'webuser ALL=(webuser) NOPASSWD: ALL' \
       > /etc/sudoers.d/webuser-self \
    && echo 'webuser ALL=(ALL) NOPASSWD: /usr/local/bin/wp, /usr/local/bin/composer, /usr/bin/npm, /usr/bin/node, /usr/bin/php' \
       >> /etc/sudoers.d/webuser-self \
    && chmod 440 /etc/sudoers.d/webuser-self

# Install Flask for container API + ClamAV for malware scanning
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip python3-flask \
        clamav clamav-daemon \
    && rm -rf /var/lib/apt/lists/* \
    || (pip3 install flask --break-system-packages) \
    # Update virus definitions on build (freshclam uses mirrors.clamav.net)
    && (freshclam --quiet || true)

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
RUN mkdir -p /var/run/mysqld \
    && chown mysql:mysql /var/run/mysqld \
    && chmod 755 /var/run/mysqld

# Disable native AIO — io_uring is blocked by Docker's default seccomp profile,
# causing MariaDB to log 'EPERM' errors and fall back slowly. Explicitly disable
# it so MariaDB uses pread/pwrite from the start.
RUN echo -e '[mysqld]\ninnodb_use_native_aio=0' \
    > /etc/mysql/mariadb.conf.d/99-container.cnf

RUN mkdir -p \
        /var/www/html \
        /var/customer/uploads \
        /var/customer/private \
        /var/customer/backups \
        /var/customer/tmp \
        /var/config/nginx \
        /var/config/php \
        /var/config/env \
        /var/config/ssl \
        /var/log/supervisor \
        /var/db \
        /var/cache/gnukontrolr/apps \
    && chown -R www-data:gnukontrolr /var/www/html \
    && chmod -R g+w /var/www/html \
    && chown -R www-data:www-data /var/customer \
    && chown gnukontrolr-admin:gnukontrolr /var/customer/tmp \
    && chmod 1777 /var/customer/tmp \
    && usermod -a -G gnukontrolr www-data \
    && chown -R gnukontrolr-admin:gnukontrolr /var/cache/gnukontrolr \
    && chmod 750 /var/cache/gnukontrolr \
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
