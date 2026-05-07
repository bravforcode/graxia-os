#!/bin/sh
# Redis entrypoint script
# Generates redis.conf with the actual password from REDIS_PASSWORD env var
# Redis config files do NOT support ${VAR} substitution natively.

set -e

if [ -z "$REDIS_PASSWORD" ]; then
    echo "ERROR: REDIS_PASSWORD environment variable is not set" >&2
    exit 1
fi

# Write redis.conf with the actual password substituted
sed "s/CHANGE_ME_SET_BY_ENTRYPOINT/${REDIS_PASSWORD}/" \
    /usr/local/etc/redis/redis.conf > /tmp/redis-runtime.conf

exec redis-server /tmp/redis-runtime.conf "$@"
