from urlparse import urlparse, ParseResult


def decode_token(token):
    if token is None:
        token = ''
    if token.startswith(('/b/', '$b$', '~b~', '[b]')):
        return (token[3:] + '==').decode('base64')
    if token.startswith(('b$', 'b~')):
        return (token[2:] + '==').decode('base64')
    return token


def decode_userpass(username=None, password=None):
    def decode_once(username, password):
        if password and not username:
            username, password = password, None
        if username and not password:
            username, _, password = username.partition(':')
        return decode_token(username), decode_token(password)
    return decode_once(*decode_once(username, password))


def encode_token(value, method='base64'):
    assert method == 'base64', 'Unknown method: {}'.format(method)
    return 'b~' + (value or '').encode('base64').rstrip('=\n')


def encode_userpass(username=None, password=None, method='base64'):
    if password and not username:
        username, password = password, None
    if username and not password:
        username, _, password = username.partition(':')
    return encode_token(encode_token(username, method) +
                        ':' + encode_token(password, method), method)


def decode_url(url):
    p = urlparse(url)
    username, password = decode_userpass(p.username, p.password)
    netloc = '%s:%s@%s' % (username, password, p.hostname)
    if p.port:
        netloc += ':%s' % p.port
    return ParseResult(p.scheme, netloc, p.path, p.params, p.query, p.fragment)
