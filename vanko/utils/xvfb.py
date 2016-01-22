import os
import re
import time
import logging
import urlparse
import urllib
import subprocess
from tempfile import TemporaryFile, NamedTemporaryFile, gettempdir

from .decode import decode_userpass
from .misc import delayed_unlink


DEF_DISPLAY = 99
DEF_VNC_PORT = -1
DEF_VNC_BASE = 5900
DEF_WM = False
DEF_SSH = ''
DEF_START = True
DEF_LOCK_ENV = True
DEF_DEBUG = False
DEF_SCREEN_RES = '800x600x15'
DEF_TEMP_DIR = gettempdir()
DEF_SSH_LOG = '.ssh.log'
DEF_DELETE_DELAY = 4


class Xvfb(object):

    logger = logging.getLogger(__name__.rpartition('.')[2])

    def __init__(self,
                 display=DEF_DISPLAY, start=DEF_START, lock_env=DEF_LOCK_ENV,
                 wm=DEF_WM, vnc_port=DEF_VNC_PORT, ssh=DEF_SSH,
                 screen_res=DEF_SCREEN_RES, debug=DEF_DEBUG):
        if ssh and vnc_port < 0:
            vnc_port = 0
        self.display = display
        self.screen_res = screen_res
        self.vnc_port = vnc_port
        self.wm = wm
        self.lock_env = lock_env
        self.ssh = ssh
        self.debug = debug
        self.use_xauth = False
        self.active = self.display >= 0

        self.proc_xvfb = self.proc_vnc = self.proc_wm = self.proc_ssh = None
        self.started = False
        if start:
            self.start()

    @classmethod
    def from_env(cls, start=DEF_START, lock_env=DEF_LOCK_ENV):
        display = int(os.environ.get('X_DISPLAY', -1))
        wm = bool(int(os.environ.get('X_WM', DEF_WM)))
        vnc_port = int(os.environ.get('X_VNC', DEF_VNC_PORT))
        ssh = os.environ.get('X_SSH', DEF_SSH)
        screen_res = os.environ.get('X_SCREEN', DEF_SCREEN_RES)
        debug = bool(int(os.environ.get('X_DEBUG', DEF_DEBUG)))
        xvfb = cls(display=display, start=start, lock_env=lock_env,
                   vnc_port=vnc_port, wm=wm, ssh=ssh,
                   screen_res=screen_res, debug=debug)
        return xvfb

    def start(self):
        if not self.active:
            return False

        # generate magic cookie
        fnull = open(os.devnull, 'r+b')
        mcookie = subprocess.check_output(
            ['mcookie'], stdin=fnull, stderr=fnull, close_fds=True)

        # choose display
        if self.display == 0:
            self.chosen_display = self.next_unused_display()
        else:
            self.chosen_display = self.display
        display_var = ':%d' % self.chosen_display

        # create authority file
        self.xauth_file = None
        if self.use_xauth:
            self.xauth_file = self.get_xauth_file_name(self.chosen_display)
            with TemporaryFile() as tmp_fd:
                open(self.xauth_file, 'wb').close()  # create empty file
                tmp_fd.write('add %s . %s\n' % (display_var, mcookie.strip()))
                tmp_fd.seek(0)
                subprocess.check_call(
                    ['xauth', 'source', '-'],
                    env={'XAUTHORITY': self.xauth_file},
                    stdin=tmp_fd, stdout=fnull, stderr=fnull, close_fds=True)

        # run xvfb
        cmd = ['Xvfb', display_var]
        cmd += ['-screen', '0', self.screen_res]
        if self.xauth_file:
            cmd += ['-auth', self.xauth_file]
        cmd += ['-nolisten', 'tcp']
        self._spawn('xvfb', cmd)

        time.sleep(0.2)
        if self.proc_xvfb.poll() is not None:
            if self.xauth_file:
                delayed_unlink(self.xauth_file, 0)
            raise RuntimeError('Xvfb failed to start')

        # setup environment
        self.started = True
        os.environ['DISPLAY'] = display_var
        if self.xauth_file:
            os.environ['XAUTHORITY'] = self.xauth_file
        if self.lock_env:
            os.environ['X_DISPLAY'] = '-1'
        self.logger.debug('xvfb serving on display %s', display_var)

        # run windows manager
        if self.wm:
            cmd = ['fluxbox']
            cmd += ['-display', display_var]
            if self.debug:
                cmd += ['-verbose']
            self._spawn('wm', cmd)

        # run vnc
        if self.vnc_port >= 0:
            vnc_port = self.vnc_port
            if vnc_port == 0:
                vnc_port = DEF_VNC_BASE + self.chosen_display
            elif vnc_port < 100:
                vnc_port += DEF_VNC_BASE
            cmd = ['x11vnc']
            cmd += ['-display', display_var]
            if self.xauth_file:
                cmd += ['-auth', self.xauth_file]
            cmd += ['-rfbport', str(vnc_port)]
            cmd += ['-nopw', '-shared', '-many', '-xkb']
            if not self.debug:
                cmd += ['-q']
            cmd += ['-ncache', '10']
            self._spawn('vnc', cmd)

        # ssh port forwarding configured by url:
        # ssh://username:password_or_key@remote_host[:ssh_port]#remote_vnc_port
        #   password_or_key:
        #     password         - plain-text password
        #     +/path/to/file   - will use ssh key from given file
        #     =environment_var - will take key from given variable
        url = urlparse.urlparse(self.ssh or '')
        if url.scheme == 'ssh' and self.vnc_port >= 0:
            username, password = decode_userpass(url.username, url.password)
            remote_port = int(url.fragment) if url.fragment else vnc_port

            pass_fd = key_fd = key_path = None
            env = os.environ.copy()
            cmd = []

            # prepare keys or passowrd
            if password.startswith('='):
                # key from environment variable
                key = env[password[1:]].strip()
                key = '\n'.join(key.split())
                key = re.sub(r'---(\w+)\n(\w+)\n(\w+)\nKEY---',
                             r'---\1 \2 \3 KEY---', key)
                key_fd = NamedTemporaryFile(prefix='.pyx11.key.', delete=False)
                delayed_unlink(key_fd.name, DEF_DELETE_DELAY)
                key_fd.write('%s\n' % key)
                key_fd.close()
                key_path = key_fd.name
            elif password.startswith('+'):
                # key from file
                key_path = urllib.unquote(password[1:])
                if not key_path:
                    key_path = url.path
            else:
                # plain text password
                pass_fd = NamedTemporaryFile(prefix='.pyx11.sh.', delete=False)
                # delete=True would render executable file busy
                delayed_unlink(pass_fd.name, DEF_DELETE_DELAY)
                pass_fd.write("#!/bin/sh\necho '%s'\n" % password)
                pass_fd.close()
                os.chmod(pass_fd.name, 0700)
                env['SSH_ASKPASS'] = pass_fd.name
                env['DISPLAY'] = 'dummy'
                cmd += ['setsid']  # prevent tty password prompt

            # construct command line
            cmd += ['ssh']
            cmd += ['-T']  # disable pseudo-tty creation
            cmd += ['-o', 'StrictHostKeyChecking=no']  # skip host key check
            if not pass_fd:
                cmd += ['-o', 'BatchMode=true']  # disable interactive prompt
            if key_path:
                cmd += ['-i', key_path]
            cmd += ['-l', username]

            cmd += ['-o', 'StrictHostKeyChecking=no']
            if not pass_fd:
                cmd += ['-o', 'BatchMode=true']
            cmd += ['-R', '%d:localhost:%d' % (remote_port, vnc_port)]

            if self.debug:
                cmd += ['-v']
            cmd += ['-p', str(url.port or 22)]
            cmd += [url.hostname]

            # spawn ssh. use pipe for stdin, else ssh exits early.
            self._spawn('ssh', cmd, env=env, pipe=True)

        return True

    def _spawn(self, name, cmd, env=None, pipe=False, debug=None):
        if debug is None:
            debug = self.debug
        if debug:
            logfile = '.pyx11.{0:d}.{1}.log'.format(os.getpid(), name)
            logfile = os.path.join(DEF_TEMP_DIR, logfile)
            self.logger.debug('starting %s: %s', name, ' '.join(cmd))
        fnull = open(os.devnull, 'r+b')
        proc = subprocess.Popen(
            cmd, env=env, close_fds=True,
            stdin=subprocess.PIPE if pipe else fnull,
            stdout=open(logfile, 'wb') if debug else fnull,
            stderr=subprocess.STDOUT if debug else fnull)
        setattr(self, 'proc_%s' % name, proc)
        return proc

    def stop(self):
        if not self.active:
            return
        for prog in ('ssh', 'vnc', 'wm', 'xvfb'):
            attr = 'proc_%s' % prog
            proc = getattr(self, attr)
            if proc:
                try:
                    proc.terminate()
                    proc.wait()
                except Exception as err:
                    self.logger.warn('error stopping %s: %s', prog, err)
            setattr(self, attr, None)

        self.started = False
        self.logger.debug('xvfb stopped on display %s', self.chosen_display)
        os.environ.pop('DISPLAY', None)
        os.environ.pop('XAUTHORITY', None)
        if self.lock_env:
            os.environ['X_DISPLAY'] = str(self.display)
        try:
            delayed_unlink(self.xauth_file, 0)
        except Exception:
            pass

    def __del__(self):
        self.stop()

    @classmethod
    def next_unused_display(cls):
        # See also: _get_next_unused_display() at:
        # https://github.com/cgoldberg/xvfbwrapper/blob/master/xvfbwrapper.py
        for display in xrange(10, 60000):
            if not os.path.exists(cls.get_xauth_file_name(display)):
                return display
        else:
            raise RuntimeError('Cannot find free display')

    @classmethod
    def get_xauth_file_name(cls, display):
        return os.path.join(DEF_TEMP_DIR, '.xvfb.Xauthority.%d' % display)
