FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    opendkim opendkim-tools \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/opendkim/keys /var/run/opendkim \
    && (groupmod -g 1001 opendkim 2>/dev/null || groupadd -r opendkim -g 1001) \
    && (usermod -u 1001 -g 1001 opendkim 2>/dev/null || useradd -r -g opendkim -s /bin/false -u 1001 -d /etc/opendkim opendkim) \
    && chown -R opendkim:opendkim /etc/opendkim /var/run/opendkim
COPY opendkim.conf /etc/opendkim/opendkim.conf
COPY trusted.hosts /etc/opendkim/trusted.hosts
EXPOSE 8891

# Run as non-root opendkim user (UID/GID 1001). The webpanel container shares
# GID 1001 via group_add so panelapi can chgrp DKIM key files to this group.
USER opendkim
CMD ["opendkim", "-f", "-x", "/etc/opendkim/opendkim.conf"]
