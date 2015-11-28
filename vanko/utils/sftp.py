import os
import tempfile
import paramiko
import logging
from os.path import abspath, relpath, normpath, join, dirname, isabs, isfile

from .decode import decode_url


class SFTPClient(object):

    logger = logging.getLogger(__name__.rpartition('.')[2])

    def __init__(self, server_url,
                 remote_dir=None, local_dir=None, debug=None):
        parts = decode_url(server_url)
        options = parts.fragment.split(',')
        if debug is None:
            debug = 'debug=1' in options

        self.server_url = server_url
        self.options = options
        self.debug = debug

        self.transport = paramiko.Transport((parts.hostname, parts.port or 22))
        self.transport.connect(username=parts.username,
                               password=parts.password)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

        if not local_dir:
            local_dir = tempfile.gettempdir()
        self.local_dir = abspath(local_dir)

        if not remote_dir:
            remote_dir = parts.path
        self.remote_dir = abspath(remote_dir)

        self.dirs_created = set(['/'])

    def _log(self, msg, *args, **kwargs):
        if self.debug:
            self.logger.info(msg, *args, **kwargs)

    def close(self):
        self.sftp.close()
        self.transport.close()

    def upload_file(self, file_name):
        if isabs(file_name):
            rel_path = relpath(file_name, self.local_dir)
        else:
            rel_path = file_name
        local_path = normpath(join(self.local_dir, rel_path))
        remote_path = normpath(join(self.remote_dir, rel_path))
        self.last_local_path = local_path
        self.last_remote_path = remote_path
        self._log('file_name=%s rel_path=%s local_path=%s remote_path=%s',
                  file_name, rel_path, local_path, remote_path)
        self._verify_local_file(local_path, file_name)
        self._make_remote_dirs(remote_path)
        self.sftp.put(local_path, remote_path)
        self._log('send %s: ok', remote_path)

    def upload_buffer(self, file_name, buf):
        if isabs(file_name):
            remote_path = normpath(file_name)
        else:
            remote_path = normpath(join(self.remote_dir, file_name))
        if not remote_path.startswith(self.remote_dir):
            raise NameError('path is outside: %s' % file_name)
        self._make_remote_dirs(remote_path)
        self._log('upload buffer %s', remote_path)
        with self.sftp.open(remote_path, 'w') as remote_file:
            remote_file.write(buf.getvalue())

    def _verify_local_file(self, local_path, file_name):
        if not local_path.startswith(self.local_dir):
            raise NameError('path is outside: %s' % file_name)
        if not os.path.exists(local_path):
            raise ValueError('file does not exist: %s' % file_name)
        if not isfile(local_path):
            raise ValueError('not a file: %s' % file_name)
        if not os.access(local_path, os.R_OK):
            raise IOError('file not readable: %s' % file_name)

    def _make_remote_dirs(self, remote_path):
        parent = dirname(remote_path)
        parents = []

        while parent and parent not in self.dirs_created:
            parents.append(parent)
            self.dirs_created.add(parent)
            parent = dirname(parent)

        for parent in reversed(parents):
            try:
                self.sftp.mkdir(parent)
            except IOError as e:
                self._log('mkdir %s: %s', parent, e)
            else:
                self._log('mkdir %s: ok', parent)
