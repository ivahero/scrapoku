# flake8: noqa
# Use json compatible with flask.json.JSONEncoder
try:
    from itsdangerous import simplejson as _json
except ImportError:
    try:
        from itsdangerous import json as _json
    except ImportError:
        import json as _json
