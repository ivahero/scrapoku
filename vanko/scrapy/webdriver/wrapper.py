import os
import sys
import logging
import tempfile
import urllib

from glob import glob
from urlparse import urlparse
from selenium import webdriver

from ...utils.xvfb import Xvfb
from .. import PersistentUserAgentMiddleware, CustomSettings

CustomSettings.register(
    WEBDRIVER_BROWSER='',
    WEBDRIVER_LOGLEVEL=-1,
    WEBDRIVER_FIX_PROXY=True,
    PHANTOMJS_BINARY='',
    CHROME_BINARY='',
    FIREFOX_PREFERENCES='',
    PROXY='',
    )

logger = logging.getLogger(__name__)


class WebdriverWrapper(object):

    webdriver_logger_name = 'selenium.webdriver.remote.remote_connection'

    def __init__(self, settings):
        self.settings = settings
        self.xvfb = None
        self.webdriver = None
        self.should_fix_proxy = self.settings.getbool('WEBDRIVER_FIX_PROXY')

    def open(self, browser=None, spider=None, implicitly_wait=None):
        if self.should_fix_proxy:
            self._proxy_workaround()
            self.should_fix_proxy = False
        self.xvfb = Xvfb.from_env()
        if browser is None:
            browser = self.settings.get('WEBDRIVER_BROWSER')
        self.webdriver = self.get_webdriver(browser, spider)
        if implicitly_wait is not None:
            self.webdriver.implicitly_wait(implicitly_wait)
        return self.webdriver

    def close(self):
        if self.webdriver:
            logger.debug('close webdriver')
            try:
                self.webdriver.quit()
            except AttributeError:
                if not self._phantomjs_quit_workaround(self.webdriver):
                    raise
                logger.debug('workaround: success')
            self.webdriver = None
        if self.xvfb:
            self.xvfb.stop()
            self.xvfb = None

    def get_proxy(self):
        proxy = getattr(self, '_proxy_url', None)
        if proxy is None:
            proxy = self.settings.get('PROXY', '')
            if not proxy:
                proxy = os.environ.get('http_proxy', '')
            if not proxy and sys.platform == 'win32':
                proxy = (urllib.getproxies_registry() or {}).get('http', '')
            if proxy and '://' not in proxy:
                proxy = 'http://' + proxy
            self._proxy_url = proxy
        return proxy

    @staticmethod
    def _proxy_workaround():
        """
        Webdriver internally connects to browser via http://127.0.0.1:port/xxx
        via proxy, if set. We set no_proxy, so that this connection is direct.
        """
        sys_proxy = 'http_proxy' in os.environ
        if not sys_proxy and sys.platform == 'win32':
            sys_proxy = 'http' in urllib.getproxies_registry()
        if sys_proxy:
            os.environ.setdefault('no_proxy', 'localhost,127.0.0.1')

    @classmethod
    def webdriver_loglevel(cls, settings=None, new_level=None, default=None):
        webdriver_logger = logging.getLogger(cls.webdriver_logger_name)
        old_level = webdriver_logger.level
        undef = (None, -1)
        if new_level in undef and settings is not None:
            new_level = settings.getint('WEBDRIVER_LOGLEVEL', -1)
        if new_level in undef and default not in undef:
            new_level = default
        if new_level not in undef:
            webdriver_logger.setLevel(new_level)
        return old_level

    def get_webdriver(self, browser=None, spider=None):
        proxy_url = self.get_proxy()
        proxy_obj = proxy_addr = proxy_auth = None
        if proxy_url:
            parsed = urlparse(proxy_url)
            if parsed.hostname:
                proxy_addr = '%s:%s' % (parsed.hostname, parsed.port or 8080)
            if parsed.username:
                proxy_auth = '%s:%s' % (parsed.username, parsed.password or '')
            proxy_obj = webdriver.Proxy(dict(
                proxyType='manual', ftpProxy=proxy_addr,
                httpProxy=proxy_addr, sslProxy=proxy_addr))

        user_agent = \
            PersistentUserAgentMiddleware.get_global_user_agent(spider)
        browser = browser or 'phantomjs'

        if browser.lower().startswith('phantomjs'):
            binary = self.settings.get('PHANTOMJS_BINARY') or browser

            log_file = os.path.join(tempfile.gettempdir(), 'phantomjs.log')

            caps = webdriver.DesiredCapabilities.PHANTOMJS.copy()
            if user_agent:
                caps['phantomjs.page.settings.userAgent'] = user_agent

            args = []
            if proxy_addr:
                args.append('--proxy=%s' % proxy_addr)
                if proxy_auth:
                    args.append('--proxy-auth=%s' % proxy_auth)

            return webdriver.PhantomJS(
                executable_path=binary, desired_capabilities=caps,
                service_args=args, service_log_path=log_file)

        if browser.lower().startswith('chrome'):
            chrome_options = webdriver.ChromeOptions()
            binary = self.settings.get('CHROME_BINARY')
            if binary:
                chrome_options.binary_location = binary
            if proxy_addr:
                chrome_options.add_argument('--proxy-server=%s' % proxy_addr)
            if user_agent:
                chrome_options.add_argument('--user-agent=%s' % user_agent)
            # Proxy authentication is not supported!
            return webdriver.Chrome(chrome_options=chrome_options)

        if browser.lower().startswith('firefox'):
            profile_dir = None
            if browser.endswith('+'):
                dirs = '~/.mozilla/firefox/*.default'.split('/')
                dirs = glob(os.path.expanduser(os.path.join(*dirs)))
                if dirs and os.path.isdir(dirs[0]):
                    profile_dir = dirs[0]
            profile = webdriver.FirefoxProfile(profile_dir)
            if user_agent:
                profile.set_preference(
                    'general.useragent.override', user_agent)
            preferences = self.settings.get('FIREFOX_PREFERENCES')
            for token in preferences.strip().split(','):
                if not token.strip():
                    continue
                pref, val = map(str.strip, token.split('=', 1))
                logger.debug('Firefox preference: "%s"="%s"', pref, val)
                profile.set_preference(pref, val)
            # Proxy authentication is not supported!
            return webdriver.Firefox(firefox_profile=profile, proxy=proxy_obj)

        raise AssertionError('Unknown webdriver browser: %s' % browser)

    @staticmethod
    def _phantomjs_quit_workaround(webdriver):
        if not (webdriver.name == 'phantomjs' and
                hasattr(webdriver, 'service')):
            return
        process = getattr(webdriver.service, 'process', None)
        if not (process and process.returncode is None):
            return
        logger.debug('workaround: terminate stale phantomjs process')
        try:
            process.terminate()
            try:
                process.kill()
            except Exception:
                pass  # may not be available on windows
            process.wait()
        except Exception as err:
            logger.debug('webdriver termination error: %s', err)
        return True
