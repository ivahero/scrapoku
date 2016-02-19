from __future__ import absolute_import
import os
import sys
import time
import signal
import atexit as _atexit
from multiprocessing.util import register_after_fork
from .multiprocessing import Process2

_mswindows = (sys.platform == 'win32')


class _BreakSignalManager(object):
    SPURIOUS_SIGNAL_SEC = 0.1
    DEBUG = bool(int(os.environ.get('DEBUG', 0)))

    def __init__(self):
        self.term_signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, 'SIGBREAK'):
            self.term_signals.append(signal.SIGBREAK)

        self.orig_handlers = {}
        self.last_handled = {}
        self.user_handler = None
        register_after_fork(self, type(self)._reset)

    def _reset(self):
        self.remove_wrapper()
        self.orig_handlers = {}
        self.last_handled = {}

    @staticmethod
    def call_handler(handler, sig, arg):
        if handler:
            try:
                func = handler.im_func
                self_arg = 1
            except AttributeError:
                func = handler
                self_arg = 0
            if func == signal.default_int_handler:
                num_args = 2
            else:
                try:
                    code = func.func_code
                    num_args = code.co_argcount
                except AttributeError:
                    num_args = 0
            num_args = max(0, num_args - self_arg)
            args = (sig, arg)[:num_args]
            handler(*args)

    def handler_wrapper(self, sig=None, arg=None):
        cur_time = time.time()
        last_time = self.last_handled.get(sig, None)
        if sig is not None and last_time is not None:
            if cur_time - last_time < self.SPURIOUS_SIGNAL_SEC:
                if self.DEBUG:
                    print '{}: ignore spurious signal {}'.format(
                        type(self).__name__, sig)
                return
            self.last_handled[sig] = cur_time

        self.call_handler(self.user_handler, sig, arg)
        self.call_handler(self.orig_handlers.get(sig, None), sig, arg)

    def install_wrapper(self, signals):
        if signals:
            for sig in self.term_signals:
                self.orig_handlers.setdefault(sig, signal.getsignal(sig))
                signal.signal(sig, self.handler_wrapper)
        Process2.set_break_handler(self.handler_wrapper)

    def remove_wrapper(self, signals):
        if signals:
            for sig, orig_handler in self.orig_handlers.items():
                signal.signal(sig, orig_handler)
            self.orig_handlers.clear()
        Process2.set_break_handler(None)

    def set_handler(self, handler, winonly=False, signals=True, atexit=False):
        if not winonly or _mswindows:
            if handler:
                self.install_wrapper(signals)
                self.user_handler = handler
                if atexit:
                    _atexit.register(handler)
            else:
                self.user_handler = None
                self.remove_wrapper(signals)


_break_manager = _BreakSignalManager()
catch_break = _break_manager.set_handler
