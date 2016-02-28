def set_trace(frame=None, qt=True):
    '''
    Set a tracepoint in the Python debugger that works with Qt
    Taken from:
    http://stackoverflow.com/questions/1736015/debugging-a-pyqt4-app
    '''
    if qt:
        try:
            from PyQt5.QtCore import pyqtRemoveInputHook
        except ImportError:
            try:
                from PyQt4.QtCore import pyqtRemoveInputHook
            except ImportError:
                pyqtRemoveInputHook = None
        try:
            if pyqtRemoveInputHook:
                pyqtRemoveInputHook()
        except Exception, e:
            print 'pyqtRemoveInputHook: %r' % e
    try:
        from ipdb import set_trace as _set_trace
    except ImportError:
        from pdb import set_trace as _set_trace
    if frame is None:
        import sys
        frame = sys._getframe().f_back
    return _set_trace(frame)


def restore_hook():
    try:
        from PyQt5.QtCore import pyqtRestoreInputHook
    except ImportError:
        from PyQt4.QtCore import pyqtRestoreInputHook
    try:
        pyqtRestoreInputHook()
    except Exception, e:
        print 'pyqtRestoreInputHook: %r' % e


bp = set_trace
