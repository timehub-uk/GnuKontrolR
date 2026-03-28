FROM alpine:3.19

RUN apk add --no-cache dnsmasq

# Default config — overridden by bind-mount at runtime
COPY dnsmasq.conf /etc/dnsmasq.conf

# Hosts file directory — mounted from host at /etc/localdns
RUN mkdir -p /etc/localdns && touch /etc/localdns/panel.hosts

EXPOSE 53/udp 53/tcp

# Run in foreground; dnsmasq re-reads addn-hosts on SIGHUP
ENTRYPOINT ["dnsmasq", "--no-daemon", "--log-queries", "--log-facility=-"]
