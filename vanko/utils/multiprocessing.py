from __future__ import absolute_import
import os
import sys
import subprocess
import threading
import multiprocessing
import signal
import time

from multiprocessing.forking import Popen as _MultiprocessingPopen

from multiprocessing import *  # noqa
__all__ = multiprocessing.__all__ + ['Process2', 'send_break_all']

_mswindows = (sys.platform == 'win32')


class _Communicate(object):
    def __init__(self, stdout=None, strip_eol=False):
        if stdout is None:
            self._stdout_arg = sys.stdout
            self._stderr_arg = sys.stderr
            self._stdout_func = None
        elif callable(stdout):
            self._stdout_arg = subprocess.PIPE
            self._stderr_arg = subprocess.STDOUT
            self._stdout_func = stdout
        else:
            self._stdout_arg = stdout
            self._stderr_arg = subprocess.STDOUT
            self._stdout_func = None
        self.strip_eol = strip_eol
        self._stdout_thread = None
        self._stdin_file = self._stdout_file = self._stderr_file = None

    def get_stdout_arg(self):
        return self._stdout_arg

    def get_stderr_arg(self):
        return self._stderr_arg

    def set_file_handles(self, stdin, stdout, stderr):
        self._stdin_file = stdin
        self._stdout_file = stdout
        self._stderr_file = stderr

    def communicate(self):
        if self._stdin_file:
            self._stdin_file.close()
            self._stdin_file = None

        if self._stdout_file:
            if self._stdout_func:
                thread = threading.Thread(
                    target=self._reader,
                    args=(self._stdout_file, self._stdout_func))
                thread.setDaemon(True)
                thread.start()
                self.stdout_thread = thread
            else:
                self._stdout_file.close()
            self._stdout_file = None

        if self._stderr_file:
            self._stderr_file.close()
            self._stderr_file = None

    def _reader(self, pipe, func):
        strip_eol = self.strip_eol
        eol_len = len(strip_eol) if isinstance(strip_eol, basestring) else 0
        while 1:
            line = pipe.readline()
            if not line:
                break
            if strip_eol:
                if eol_len:
                    if line[-eol_len:] == strip_eol:
                        line = line[:-eol_len]
                else:
                    if line[-2:] == '\r\n':
                        line = line[:-2]
                    elif line[-1] in ('\r', '\n'):
                        line = line[:-1]
            func(line)
        pipe.close()


if not _mswindows:

    assert sys.version_info[:3] >= (2, 7, 8), \
        'Process2 does not yet support this Python version on Unix'

    class _RedirectedPopen(_MultiprocessingPopen):
        def __init__(self, process_obj):
            sys.stdout.flush()
            sys.stderr.flush()
            self.returncode = None
            comm = getattr(process_obj, '_comm', _Communicate())

            stdout_arg = comm.get_stdout_arg()
            rfd = wfd = close_wfd = -1
            if stdout_arg == subprocess.PIPE:
                rfd, wfd = os.pipe()
                close_wfd = wfd
            elif stdout_arg != sys.stdout:
                if isinstance(stdout_arg, int):
                    wfd = stdout_arg
                else:
                    wfd = stdout_arg.fileno()

            stderr_arg = comm.get_stderr_arg()
            redirect_stderr = (stderr_arg == subprocess.STDOUT)

            self.pid = os.fork()
            if self.pid == 0:
                out_fd = sys.stdout.fileno()
                err_fd = sys.stderr.fileno()
                if rfd != -1:
                    os.close(rfd)
                if wfd != -1:
                    os.dup2(wfd, out_fd)
                if redirect_stderr:
                    os.dup2(out_fd, err_fd)

                if 'random' in sys.modules:
                    import random
                    random.seed()
                code = process_obj._bootstrap()
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(code)

            pipe_stdin = pipe_stdout = pipe_stderr = None
            if close_wfd != -1:
                os.close(close_wfd)
            if rfd != -1:
                pipe_stdout = os.fdopen(rfd)
            comm.set_file_handles(pipe_stdin, pipe_stdout, pipe_stderr)


if _mswindows:

    assert sys.version_info[:3] == (2, 7, 11), \
        'Process2 does not yet support this Python version on Windows'

    import msvcrt

    class _RedirectedPopen(_MultiprocessingPopen):  # noqa
        def __init__(self, process_obj):
            # do not thrash module namespace, make imports here
            from multiprocessing.forking import (
                dump, HIGHEST_PROTOCOL, close, duplicate, _python_exe,
                get_command_line, get_preparation_data)

            # create pipe for communication with child
            rfd, wfd = os.pipe()

            # get handle for read end of the pipe and make it inheritable
            rhandle = duplicate(msvcrt.get_osfhandle(rfd), inheritable=True)
            os.close(rfd)

            # start process
            cmd = get_command_line() + [rhandle]
            cmd = ' '.join('"%s"' % x for x in cmd)

            comm = getattr(process_obj, '_comm', _Communicate())
            p = subprocess.Popen(
                cmd, executable=_python_exe, stdin=open(os.devnull),
                stdout=comm.get_stdout_arg(), stderr=comm.get_stderr_arg())

            # Restrain subprocess.Popen.__del__() from handling the process
            # by faking it think a child was not created
            p._child_created = False

            # Steal file handles
            comm.set_file_handles(p.stdin, p.stdout, p.stderr)

            # set attributes of self
            self.pid = p.pid
            self.returncode = None
            self._handle = p._handle

            close(rhandle)
            del p

            # send information to child
            prep_data = get_preparation_data(process_obj._name)
            to_child = os.fdopen(wfd, 'wb')
            _MultiprocessingPopen._tls.process_handle = int(self._handle)
            try:
                dump(prep_data, to_child, HIGHEST_PROTOCOL)
                process_obj._comm = _Communicate()  # don't pickle this
                dump(process_obj, to_child, HIGHEST_PROTOCOL)
            finally:
                process_obj._comm = comm
                del _MultiprocessingPopen._tls.process_handle
                to_child.close()


class Process2(Process):
    _Popen = _RedirectedPopen
    _break_handler = None

    def __init__(self, stdout=None, strip_eol=False, args=(), *_args, **_kw):
        self._comm = _Communicate(stdout, strip_eol)
        self._break = None
        if _mswindows:
            self._break = multiprocessing.Event()
            args += (self._break,)
        super(Process2, self).__init__(args=args, *_args, **_kw)

    def start(self):
        super(Process2, self).start()
        self._comm.communicate()
        return self

    def run(self):
        if _mswindows:
            self._break = self._args[-1]
            self._args = self._args[:-1]
            thread = threading.Thread(
                target=self._break_waiter, args=(self._break,))
            thread.setDaemon(True)
            thread.start()
        super(Process2, self).run()

    def _break_waiter(self, break_):
        if break_:
            break_.wait()
            if break_.is_set():
                handler = type(self)._break_handler
                if handler:
                    handler()

    @classmethod
    def set_break_handler(cls, handler):
        cls._break_handler = handler

    def send_break(self, timeout=0, force=False, winonly=False):
        if not self.is_alive():
            return self._popen.returncode

        if _mswindows:
            send_sig = signal.CTRL_C_EVENT
            should_block_echo_sig = True
            windows_error = WindowsError
        else:
            send_sig = None if winonly else signal.SIGINT
            should_block_echo_sig = False
            windows_error = IOError  # dummy exception, will not happen

        if timeout is None or timeout < 0:
            timeout = 1e9
        pid = self.pid
        raise_intr = True
        cur_time = time.time()
        end_time = cur_time + timeout

        while 1:
            try:
                t = end_time - cur_time
                if send_sig is not None:
                    sig = send_sig
                    send_sig = None
                    raise_intr = not should_block_echo_sig
                    try:
                        os.kill(pid, sig)
                    except windows_error:
                        # WindowsError(6, 'The handle is invalid')
                        # Failed to send CTRL_C_EVENT without console.
                        if self._break:
                            self._break.set()
                if t <= 0:
                    break
                if not self.is_alive():
                    break
                self.join(min(t, 2))
            except KeyboardInterrupt:
                if raise_intr:
                    raise
                raise_intr = True
            cur_time = time.time()

        if self._popen.returncode is None and force:
            self.terminate()
            self.join(0.01)
            if self._popen.returncode is None and not _mswindows:
                self.join(0.1)
                if self._popen.returncode is None:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
                    try:
                        self.join(0.01)
                    except Exception:
                        pass

        return self._popen.returncode


def send_break_all(processes, timeout=0, force=False, winonly=False):
    threads = set()
    results = {}

    def stop_process(proc):
        results[proc.pid] = proc.send_break(timeout, force, winonly)

    for p in processes:
        t = threading.Thread(target=Process2.send_break,
                             args=(p, timeout, force, winonly))
        t.start()
        threads.add(t)

    for t in threads:
        t.join()

    return results
