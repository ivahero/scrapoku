"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

# Default values.
REDIS_URL = None
REDIS_HOST = 'localhost'
REDIS_PORT = 6379


def from_settings(settings_or_url):
    from redis import Redis

    if isinstance(settings_or_url, basestring):
        return Redis.from_url(settings_or_url)
    if settings_or_url.get('REDIS_URL',  REDIS_URL):
        return Redis.from_url(settings_or_url.get('REDIS_URL',  REDIS_URL))
    else:
        return Redis(host=settings_or_url.get('REDIS_HOST', REDIS_HOST),
                     port=settings_or_url.getint('REDIS_PORT', REDIS_PORT))
