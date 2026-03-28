#!/bin/bash
# Build webpanel/php-site images for all supported PHP versions.
# Usage: ./build-all.sh [8.1|8.2|8.3|all]
set -e
VERSIONS="${1:-all}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

build_version() {
    local ver="$1"
    echo "==> Building webpanel/php-site:${ver} ..."
    docker build \
        --build-arg PHP_VERSION="${ver}" \
        -t "webpanel/php-site:${ver}" \
        "${SCRIPT_DIR}"
    echo "==> Done: webpanel/php-site:${ver}"
}

if [ "$VERSIONS" = "all" ]; then
    for v in 8.1 8.2 8.3; do
        build_version "$v"
    done
else
    build_version "$VERSIONS"
fi

echo ""
echo "Built images:"
docker images | grep "webpanel/php-site"
