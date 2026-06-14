FROM alpine:3.24

RUN apk add --no-cache dnsmasq && \
    adduser -D -u 1001 -h /etc/localdns localdns

# Default config — overridden by bind-mount at runtime
COPY dnsmasq.conf /etc/dnsmasq.conf

# Hosts file directory — mounted from host at /etc/localdns
RUN mkdir -p /etc/localdns && touch /etc/localdns/panel.hosts && \
    chown -R localdns:localdns /etc/localdns

EXPOSE 53/udp 53/tcp

USER localdns

# Run in foreground; dnsmasq re-reads addn-hosts on SIGHUP
ENTRYPOINT ["dnsmasq", "--no-daemon", "--log-queries", "--log-facility=-"]
