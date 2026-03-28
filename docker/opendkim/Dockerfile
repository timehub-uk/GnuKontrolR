FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    opendkim opendkim-tools \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/opendkim/keys /var/run/opendkim
COPY opendkim.conf /etc/opendkim/opendkim.conf
COPY trusted.hosts /etc/opendkim/trusted.hosts
EXPOSE 8891
# Run as root so it can read private key files written by the panel API
# container (different UID). The keys volume is not host-accessible.
CMD ["opendkim", "-f", "-x", "/etc/opendkim/opendkim.conf"]
