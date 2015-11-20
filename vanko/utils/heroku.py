import os
import sys
import re
import json
import time
import requests
import httplib
import logging

from .decode import decode_token


class HerokuRestart(object):

    API_URL = 'https://api.heroku.com/apps'
    RESTART_SEC = 11
    MODULE = '%s.%s' % (__package__,
                        os.path.splitext(os.path.basename(__file__))[0])
    DEBUG = False
    SHELL = True

    logger = logging.getLogger(__name__.rpartition('.')[2])

    def __init__(self, app=None, dyno=None, token=None,
                 debug=None, shell=None, now=False):
        self.app = app or os.environ.get('APP_NAME', '-')
        self.dyno = dyno or os.environ.get('DYNO', '-')
        self.token = token or os.environ.get('APP_TOKEN', '-')
        self.debug = debug if debug is not None else self.DEBUG
        self.shell = shell if shell is not None else self.SHELL

        self.headers = {
            'Accept': 'application/vnd.heroku+json; version=3',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % decode_token(self.token)
        }

        if self.debug:
            httplib.HTTPConnection.debuglevel = 1
            self.logger.debug(
                '%s(app=%s dyno=%s token=%s)',
                type(self).__name__, self.app, self.dyno, self.token)
        if now:
            self.restart()

    def restart(self, stop_delay=None, command=None, dyno=None):
        if command is None:
            command = self.get_command(quote=True, dyno=dyno)
        method = 'shell' if self.shell else 'api'
        dyno = dyno or self.dyno
        cmdline = 'python -m {mod} {meth} {app} {dyno} {token} {cmd}'.format(
            mod=self.MODULE, meth=method, app=self.app,
            dyno=dyno, token=self.token, cmd=command)
        if self.debug:
            self.logger.debug('cmdline: %s', cmdline)
        if stop_delay is not None:
            self.stop(delay=stop_delay, dyno=dyno)
        return self.run(cmdline)

    def get_url(self, dyno=None):
        return '{api}/{app}/dynos/{dyno}'.format(
            api=self.API_URL, app=self.app, dyno=(dyno or self.dyno).strip())

    def get_command(self, quote=False, dyno=None):
        dyno = dyno or self.dyno
        res = requests.get(self.get_url(dyno), headers=self.headers)
        if res.status_code != httplib.OK:
            raise ValueError(
                'Dyno {} not found ({})'.format(dyno, res.status_code))
        command = res.json()['command']
        self.logger.debug('Current command is %r', command)
        mo = re.match(r'python -m %s (?:\S+ ){4}(\'.*\')' % self.MODULE,
                      command)
        if mo:
            command = mo.group(1)[1:-1].replace("'\\''", "'")
        if quote:
            command = "'" + command.replace("'", "'\\''") + "'"
        return command

    def run(self, command=None):
        url = self.get_url().rpartition('/')[0]
        if command is None:
            command = self.get_command(quote=True)
        data = json.dumps({'attach': False, 'command': command})
        if self.debug:
            self.logger.debug('run: %s', command)
        res = requests.post(url, headers=self.headers, data=data)
        if res.status_code != httplib.CREATED:
            raise RuntimeError(
                'Cannot start dyno [{}] ({})'.format(command, res.status_code))
        return self

    def stop(self, delay=0, dyno=None):
        if not dyno and self.dyno.startswith('web.'):
            self.logger.info('Will not stop dyno %s', self.dyno)
            return
        url = self.get_url(dyno)
        if self.debug:
            self.logger.debug('Stopping %s', url)
        res = requests.delete(url, headers=self.headers)
        if res.status_code != httplib.ACCEPTED:
            raise RuntimeError('Cannot stop dyno {} ({})'.format(
                dyno or self.dyno, res.status_code))
        if self.debug:
            self.logger.debug('Waiting %d seconds', delay)
        start = time.time()
        while delay > 0 and time.time() < start + delay:
            time.sleep(0.5)
        return self

    def list(self, include=None, exclude=None):
        res = requests.get(self.get_url(' '), headers=self.headers)
        if res.status_code != httplib.OK:
            raise RuntimeError(
                'Cannot list dynos ({})'. format(res.status_code))
        _dynos = [str(item['name']) for item in res.json()]
        dynos = []
        for d in _dynos:
            if include and d.startswith(include):
                dynos.append(d)
            elif exclude and d.startswith(exclude):
                continue
            else:
                dynos.append(d)
        return sorted(dynos)

    def stop_many(self, include=None, exclude=None, delay=0):
        if not include and not exclude:
            exclude = 'web.'
        dynos = self.list(include, exclude)
        results = {}
        for d in dynos:
            try:
                self.stop(delay=delay, dyno=d)
                results[d] = True
            except Exception, e:
                results[d] = e
        return results

    def _main(self, command, method='shell'):
        try:
            self.stop(delay=self.RESTART_SEC)
        except RuntimeError as err:
            self.logger.warning(err)
        if method == 'shell':
            if self.debug:
                self.logger.debug('shell: %s', command)
            os.system(command)
        else:
            self.run(command)
        return self

    @classmethod
    def main(cls, arg=sys.argv):
        logging.basicConfig(
            format='%(asctime)s [restart] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S', stream=sys.stdout,
            level=logging.DEBUG if cls.DEBUG else logging.INFO)
        if len(arg) == 6 and arg[1] in ('api', 'shell'):
            instance = cls(app=arg[2], dyno=arg[3], token=arg[4])
            instance._main(command=arg[5], method=arg[1])
        else:
            sys.exit('usage: python -m %s spawn|api '
                     '[<app> <dyno> <token>] <command>' % cls.MODULE)

if __name__ == '__main__':
    HerokuRestart.main()
