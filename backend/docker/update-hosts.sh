#!/bin/sh
# Helper to add/remove /etc/hosts entries.
# Called by panelapi via sudo.
case "$1" in
  add)
    shift
    echo "$1    $2" >> /etc/hosts
    echo "HOSTS: added $2 -> $1"
    ;;
  remove)
    shift
    host="$1"
    # Use grep -v to filter out the line and write to a temp file,
    # then replace since sed -i fails on some mounts.
    grep -v " $host$" /etc/hosts > /etc/hosts.tmp && \
      cat /etc/hosts.tmp > /etc/hosts && \
      rm -f /etc/hosts.tmp
    echo "HOSTS: removed $host"
    ;;
  *)
    echo "Usage: $0 add <ip> <hostname> | remove <hostname>"
    exit 1
    ;;
esac
