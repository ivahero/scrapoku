import os
import time
import threading
import itertools


class LogWatcher(object):
    BUFLEN = 4096

    def __init__(self, func, path=None, arg_path=False, poll_sec=1.0):
        self.func = func
        self.arg_path = arg_path
        self.poll_sec = poll_sec
        self.next_id = itertools.count(1)
        self.children = {}
        self.running = True
        if path:
            self.watch(path)

    def watch(self, path):
        if not path:
            return
        cid = self.next_id.next()
        thread = threading.Thread(target=self._watcher, args=(cid, path))
        thread.setDaemon(False)
        self.children[cid] = {'path': path, 'thread': thread, 'active': True}
        thread.start()
        return True

    def unwatch(self, path):
        count = 0
        for cid in self.children.keys():
            if self.children[cid]['path'] == path:
                self.children[cid]['active'] = False
                count += 1
        return count

    def stop(self):
        self.running = False
        for cid in self.children.keys():
            self.children[cid]['thread'].join()
        self.children = {}

    def __del__(self):
        self.stop()

    def _watcher(self, cid, path):
        fd = None
        ino = -1
        sz = 0
        while self.running and cid in self.children \
                and self.children[cid]['active']:
            time.sleep(self.poll_sec)
            while 1:
                text = ''
                if fd:
                    text = fd.read(self.BUFLEN)
                if not text:
                    try:
                        st = os.stat(path)
                    except IOError:
                        break
                    if sz == st.st_size and ino == st.st_ino:
                        break
                    if fd:
                        fd.close()
                    fd = None
                    try:
                        fd = open(path, 'rb')
                    except IOError:
                        break
                    else:
                        ino = st.st_ino
                    if sz < st.st_size:
                        fd.seek(sz)
                    else:
                        sz = 0
                    text = fd.read(self.BUFLEN)
                    if not text:
                        break
                sz += len(text)
                if self.arg_path:
                    self.func(path, text)
                else:
                    self.func(text)
