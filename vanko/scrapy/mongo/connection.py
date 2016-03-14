
def from_settings(settings_or_url):
    from pymongo import MongoClient

    if isinstance(settings_or_url, basestring):
        url = settings_or_url
    else:
        url = settings_or_url.get('MONGODB_URL')
    return MongoClient(url).get_default_database()
