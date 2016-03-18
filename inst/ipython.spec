# -*- mode: python -*-

project = 'ipython'
modules = ['../vanko/utils/ipython.py']
datas = []
upx_coll = True
upx_exe = True
console = True
onefile = True
block_cipher = None

import os, sys
exe_name = project if onefile else 'runme'

a = Analysis(modules,
             pathex=[], binaries=None,
             datas=datas,
             hiddenimports=[],
             hookspath=['inst/hooks'],
             runtime_hooks=[], excludes=[],
             win_no_prefer_redirects=False, win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if onefile:
  exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
            name=exe_name, debug=False, strip=False, upx=upx_exe, console=console)
else:
  exe = EXE(pyz, a.scripts, exclude_binaries=True,
            name=exe_name, debug=False, strip=False, upx=upx_exe, console=console)
  coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
                 name=project, strip=False, upx=upx_coll)
