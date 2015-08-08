from __future__ import print_function, absolute_import

if True:
    import warnings
    warnings.filterwarnings('ignore')

if True:
    from . import defs
if defs.WT_VIRTUAL_DISPLAY:
    try:
        from pyvirtualdisplay import Display
        Display(visible=True, size=(800, 600), color_depth=16).start()
    except:
        pass

try:
    from __main__ import global_app
except:
    from PyQt4 import QtGui
    global_app = QtGui.QApplication([])

try:
    import qt4reactor
    qt4reactor.install()
except:
    pass

if True:
    from twisted.internet import reactor, defer
    from twisted.internet.error import TimeoutError
    import random
    import logging
    from datetime import datetime
    from PyQt4 import QtCore
    from PyQt4 import QtGui
    from PyQt4 import QtNetwork
    from PyQt4 import QtWebKit
    from .utils import qwebkit_settings


class QtCrawler(QtWebKit.QWebPage):
    # based on:
    # http://webscraping.com/blog/Scraping-JavaScript-webpages-with-webkit/

    def __init__(self, show=None, settings=None):
        super(QtCrawler, self).__init__()

        self._url = '-'
        self._settings = qwebkit_settings(settings)
        self._verbose = self._settings.getbool('WT_VERBOSE')
        self._show = self._settings.getbool('WT_SHOW') \
            if show is None else bool(show)

        self.loadFinished.connect(self._on_load_finished)

        self._user_agent = self._settings.get('WT_USER_AGENT')

        netman = QtNetwork.QNetworkAccessManager()
        self._cookiejar = QtNetwork.QNetworkCookieJar()
        netman.setCookieJar(self._cookiejar)
        netman.finished.connect(self._on_reply_received)
        self.setNetworkAccessManager(netman)

        if self._show:
            view = QtWebKit.QWebView()
            view.setPage(self)
            view.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            view.destroyed.connect(self._on_window_close)
            view.show()
            self._view = view
        else:
            self.setViewportSize(QtCore.QSize(800, 600))

        self._timer = QtCore.QTimer(self)
        self._log('crawler page created (show=%s)' % self._show)

    def _on_window_close(self):
        self._log('crawler window closed')
        try:
            reactor.callLater(0, reactor.stop)
        except:
            pass

    def crawl(self, kwargs):
        # deferred like
        # http://stackoverflow.com/questions/12504311/\
        # how-to-keep-python-qtwebkit-instance-running-and-persistent
        self._url = kwargs.get('url')
        self._log('crawl started')

        self._scroll_timeout = kwargs.get('scroll_timeout', 0)
        self._max_height = kwargs.get('max_height', 0)
        self._page_timeout = kwargs.get(
            'page_timeout', self._settings.getint('WT_PAGE_TIMEOUT'))
        self._verbose = kwargs.get('verbose', self._verbose)

        self._last_height = 0
        self._last_stamp = datetime.now()
        self._load_is_finished = False

        self._set_proxy(kwargs.get('proxy', ''))
        self._set_load_images(kwargs.get(
            'load_images', self._settings.getbool('WT_LOAD_IMAGES')))
        self._set_user_agent(kwargs.get('user_agent'))
        self._set_all_cookies_from_strings(kwargs.get('cookie_strings', None))

        self._result = dict(body='', cookies='', headers=[])
        self._response_headers = []
        self._deferred = defer.Deferred()

        self._log('request issued')
        self.mainFrame().load(QtCore.QUrl(self._url))

        if self._page_timeout and self._page_timeout > 0:
            self._timer.singleShot(int(1000 * self._page_timeout),
                                   self._on_load_failed)

        return self._deferred

    def userAgentForUrl(self, url):
        return self._user_agent

    def is_shown(self):
        return self._show

    def get_id(self):
        return hex(hash(self))[2:]

    def _set_load_images(self, load_images):
        from PyQt4.QtWebKit import QWebSettings
        settings = self.settings()
        settings.setAttribute(QWebSettings.AutoLoadImages, load_images)
        settings.setAttribute(QWebSettings.JavaEnabled, False)
        settings.setAttribute(QWebSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebSettings.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebSettings.PluginsEnabled, False)

    def _set_proxy(self, proxy):
        from PyQt4.QtNetwork import QNetworkProxy
        if proxy is None:
            return
        elif proxy == '':
            qnproxy = QNetworkProxy()
        else:
            proxy = proxy.replace('http://', '').replace('https://', '')
            if ':' in proxy:
                phost, pport = proxy.split(':')
            else:
                phost, pport = proxy, 8080
            qnproxy = QNetworkProxy(QNetworkProxy.HttpProxy, phost, int(pport))
            self._log('proxy is %s:%s' % (phost, pport))
        self.networkAccessManager().setProxy(qnproxy)

    def _set_user_agent(self, user_agent):
        if user_agent is None:
            self._user_agent = self._settings.get('WT_USER_AGENT')
        elif user_agent == '*':
            self._user_agent = random.choice(
                self._settings.getlist('WT_USER_AGENT_LIST'))
        elif user_agent != '':
            self._user_agent = user_agent

    def _log(self, msg):
        if self._verbose:
            logging.debug('[%s] [%s] %s' % (self._url, self.get_id(), msg))

    def _run_js(self, js):
        return self.mainFrame().documentElement().evaluateJavaScript(js)

    def _set_all_cookies_from_strings(self, cookie_string_list):
        if cookie_string_list is None:
            return
        if isinstance(cookie_string_list, basestring):
            cookie_string = cookie_string_list
        else:
            cookie_string = '; '.join(cookie_string_list)
        cookie_list = []
        for pair in cookie_string.split(';'):
            if '=' in pair:
                key, val = pair.strip().split('=', 1)
            else:
                key, val = pair, ''
            cookie_list.append(QtNetwork.QNetworkCookie(key, val))
        self._cookiejar.setAllCookies(cookie_list)

    def _get_cookie_string(self):
        lst = []
        key2no = {}
        compact_cookies = self._settings.get('WT_COMPACT_COOKIES')
        for c in self._cookiejar.allCookies():
            key = str(c.name())
            raw = str(c.toRawForm(c.Full))
            if compact_cookies and key in key2no:
                if len(raw) > len(lst[key2no[key]]):
                    lst[key2no[key]] = raw
            else:
                key2no[key] = len(lst)
                lst.append(raw)
        return '\n'.join(lst)

    def _get_all_cookies(self):
        for c in self._cookiejar.allCookies():
            yield dict(name=str(c.name()),
                       value=str(c.value()),
                       domain=str(c.domain()),
                       httpOnly=c.isHttpOnly(),
                       secure=c.isSecure(),
                       expires=str(
                           c.expirationDate().toString('yyyy-MM-dd hh:mm:ss'))
                       )

    def _get_height(self, redraw=None):
        if redraw is None:
            redraw = not self._show
        if redraw:
            pixmap = QtGui.QPixmap(1, 1)
            paint = QtGui.QPainter(pixmap)
            self.mainFrame().render(paint)
            paint.end()
        return self._run_js('document.body.scrollHeight').toInt()[0]

    def _on_reply_received(self, reply):
        url = reply.request().url().toString()
        if self._url == url:
            self._log('reply received for %s' % url)
            self._response_headers = [(str(hdr), str(val))
                                      for hdr, val in reply.rawHeaderPairs()]

    def _on_load_finished(self, result):
        if not self._load_is_finished:
            self._load_is_finished = True
            self._log('body loading finished')
            if self._scroll_timeout > 0:
                self._get_height(redraw=None)
                self._timer.timeout.connect(self._check_page_cb)
                check_interval = self._settings.getfloat('WT_CHECK_INTERVAL')
                self._timer.start(int(1000 * check_interval))
                self._last_stamp = datetime.now()
            else:
                self._done()
        else:
            self._log('got fake loading finished')
            pass

    def _check_page_cb(self):
        last_height = self._last_height
        new_height = self._last_height = self._get_height(redraw=False)
        new_stamp = datetime.now()
        seconds = int((new_stamp - self._last_stamp).total_seconds())
        self._log('height changed to %s after %.1f seconds'
                  % (new_height, seconds))
        if new_height > last_height:
            self._last_stamp = new_stamp
            self._run_js('window.scrollTo(0,document.body.scrollHeight);')
        if 0 < self._max_height < new_height \
                or 0 < self._scroll_timeout < seconds:
            self._done()

    def _done(self, result=None):
        if result is None:
            result = dict(body=unicode(self.mainFrame().toHtml()),
                          cookies=self._get_cookie_string(),
                          headers=self._response_headers[:])
        self._timer.stop()
        if self._deferred is not None:
            self._deferred.callback(result)
        self._deferred = None

    def _on_load_failed(self):
        msg = 'Getting %s took longer than %s seconds.' \
              % (self._url, self._page_timeout)
        if self._settings.getbool('WT_RAISE_ON_TIMEOUT'):
            raise TimeoutError(msg)
        else:
            self._log(msg)
            self._done(result=dict(body='', cookies='', headers=[]))
