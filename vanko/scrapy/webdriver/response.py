import re
import logging
from time import time, sleep
from scrapy import Selector

from selenium.webdriver.common.by import By
from selenium.webdriver.support import ui
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import InvalidSelectorException
from selenium.common.exceptions import WebDriverException

logger = logging.getLogger()


class WebdriverResponseMixin(object):

    implicitly_wait = 30
    poll_sec = 1.0

    def load_page(self, url):
        self.clear_cache()
        return self.webdriver.get(url)

    def clear_cache(self, safe=False):
        if safe:
            try:
                self._cached_selector = None
            except Exception as e:
                return e
        else:
            self._cached_selector = None

    @property
    def selector(self):
        if getattr(self, '_cached_selector', None) is None:
            self._cached_selector = self.get_page_selector()
        return self._cached_selector

    def get_body(self):
        return self.webdriver.page_source

    def get_page_selector(self):
        return Selector(text=self.get_body())

    def find_element_by_id(self, element_id):
        return self.webdriver.find_element_by_id(element_id)

    def remove_class(self, el, classes='*'):
        if classes:
            get_el = 'document.getElementById("%s")' % el.get_attribute('id')
            if classes == '*':
                script = '%s.removeAttribute("class");' % get_el
            else:
                class_list = el.get_attribute('class').split()
                class_list.remove(classes)
                new_cls = ' '.join(class_list)
                script = '%s.setAttribute("class", "%s");' % (get_el, new_cls)
            self.webdriver.execute_script(script)

    def remove_attr(self, el, attributes='readonly'):
        if attributes:
            get_el = 'document.getElementById("%s")' % el.get_attribute('id')
            script = ''
            for attr_name in attributes.split():
                script += '%s.removeAttribute("%s");' % (get_el, attr_name)
            self.webdriver.execute_script(script)

    def fix_focus(self, delay=None):
        if delay is None:
            delay = 0.5
        delay /= 2.
        sleep(delay)
        try:
            body = self.webdriver.find_element_by_tag_name('body')
            body.click()
        except WebDriverException as err:
            logger.debug('body click missed: %s', str(err))
        sleep(delay)

    def click_select(self, select, option, method=None,
                     timeout=None, min_list_len=None):
        if method is None:
            method = 'text'
        assert method in ('text', 'click', 'index'), \
            'Invalid method: {}'.format(method)
        assert method != 'index' or isinstance(option, int), \
            'Index option must be int'

        if timeout is None:
            timeout = self.implicitly_wait

        el_option = text = None

        if isinstance(option, int):
            if option < 0:
                option += len(select.options)
            if method != 'index':
                el_option = select.options[option]
        elif isinstance(option, (str, unicode)):
            method = 'text'
            text = option
        else:
            el_option = option
            option = option.id

        if min_list_len is not None:
            if len(select.options) < min_list_len:
                raise IndexError('Select has {} options, must be {}'.format(
                                 len(select.options), min_list_len))

        try:
            if method == 'index':
                select.select_by_index(option)
            elif method == 'text':
                if text is None:
                    text = el_option.text
                select.select_by_visible_text(text)
            elif method == 'click':
                el_option.click()
        except ValueError as err:
            # FIXME: Bug: https://github.com/SeleniumHQ/selenium/issues/1478
            msg = err.message
            logger.debug('Click failed (ValueError): %s', msg)
            if 'No JSON object could be decoded' in msg:
                raise StaleElementReferenceException(msg)
            raise
        except TypeError as err:
            # FIXME: Bug: https://github.com/SeleniumHQ/selenium/issues/1497
            msg = err.message
            logger.debug('Click failed (TypeError): %s', msg)
            if 'string indices must be integers' in msg:
                raise StaleElementReferenceException(msg)
            raise

        if el_option is not None:
            selected = WebDriverWait(self.webdriver, timeout).until(
                ec.element_to_be_selected(el_option))
        else:
            selected = '<unknown>'

        logger.debug('click_select(%s, %s)=%s',
                     select._el.id, option, selected)
        return selected

    def click_select_safe(self, element_id, option, name=None, method=None,
                          min_list_len=None, timeout=None):
        if name is None:
            name = element_id
        if timeout is None:
            timeout = self.implicitly_wait
        poll_sec = self.poll_sec

        logger.debug('fill %s', name)
        end_wait = time() + timeout

        while time() < end_wait:
            try:
                el_sel = WebDriverWait(self.webdriver, timeout).until(
                    ec.element_to_be_clickable((By.ID, element_id)))
                sel = ui.Select(el_sel)
            except StaleElementReferenceException as err:
                msg = str(err).rstrip()
                logger.debug('pending %s selector (%s)', name, msg)
                sleep(poll_sec)
                continue

            try:
                selected = self.click_select(sel, option, timeout=timeout,
                                             min_list_len=min_list_len)
                if selected:
                    break
            except (IndexError, StaleElementReferenceException) as err:
                msg = str(err).rstrip()
                logger.debug('pending %s options (%s)', name, msg)
                sleep(poll_sec)
                continue
        else:
            raise InvalidSelectorException('Cannot select departure time')

    def click_safe(self, element_id, by=By.ID, timeout=None):
        if timeout is None:
            timeout = self.implicitly_wait
        el = WebDriverWait(self.webdriver, timeout).until(
            ec.element_to_be_clickable((by, element_id)))
        logger.debug('now click %s', element_id)
        el.click()

    def send_keys_safe(self, element_id, keys, timeout=None):
        if timeout is None:
            timeout = self.implicitly_wait
        poll_sec = self.poll_sec
        end_wait = time() + timeout
        while time() < end_wait:
            try:
                el = self.webdriver.find_element_by_id(element_id)
                el.clear()
                el.send_keys(keys)
                break
            except WebDriverException as err:
                msg = str(err).rstrip()
                logger.debug('Cannot send keys: %s', msg)
                if re.search(r"'?undefined'? is not an object", msg):
                    sleep(poll_sec)
                    continue
                raise
        else:
            raise WebDriverException('Cannot send keys')

    def get_ajax_activity(self):
        counts = self.webdriver.execute_script(
            'return [window.jQuery && window.jQuery.active, '
            'window.Ajax && window.Ajax.activeRequestCount, '
            'window.dojo && window.io.XMLHTTPTransport.inFlight.length];')
        logger.debug('active ajax requests: %s', counts)
        return sum(n for n in counts if n is not None)

    def wait_for_ajax(self, timeout=None, poll_sec=None, trigger='end'):
        if timeout is None:
            timeout = self.implicitly_wait
        if poll_sec is None:
            poll_sec = self.poll_sec
        logger.debug('wait for ajax to %s (%ss)', trigger, timeout)

        if trigger == 'start':
            def is_pending(flag):
                return not flag
        elif trigger == 'end':
            def is_pending(flag):
                return flag
        else:
            raise ValueError('invalid trigger: %s', trigger)

        end_time = time() + timeout
        while is_pending(self.get_ajax_activity()):
            if time() >= end_time:
                return False
            sleep(poll_sec)
        return True

    def wait_css(self, css, timeout=None, poll_sec=None):
        if timeout is None:
            timeout = self.implicitly_wait
        if poll_sec is None:
            poll_sec = self.poll_sec
        cur_time = time()
        end_time = cur_time + timeout
        while 1:
            result = self.css(css)
            if result:
                return result
            self.clear_cache()
            cur_time = time()
            if cur_time >= end_time:
                return
            sleep(min(self.poll_sec, end_time - cur_time))
