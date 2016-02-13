"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

import redis


# Default values.
REDIS_URL = None
REDIS_HOST = 'localhost'
REDIS_PORT = 6379


def from_settings(settings):
    url = settings.get('REDIS_URL',  REDIS_URL)
    host = settings.get('REDIS_HOST', REDIS_HOST)
    port = settings.get('REDIS_PORT', REDIS_PORT)

    # REDIS_URL takes precedence over host/port specification.
    if url:
        return redis.from_url(url)
    else:
        return redis.Redis(host=host, port=port)
