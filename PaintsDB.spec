# Build from a clean, locked Windows x64 environment.
from PyInstaller.utils.hooks import copy_metadata

datas = [('paintsdb/ui', 'paintsdb/ui'), ('paintsdb/schema.sql', 'paintsdb')]
datas += copy_metadata('mcp') + copy_metadata('pywebview')
a = Analysis(['main.py'], pathex=[], binaries=[], datas=datas,
    hiddenimports=['webview.platforms.qt', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                   'PySide6.QtWebChannel', 'uvicorn.logging', 'uvicorn.loops.asyncio',
                   'uvicorn.protocols.http.h11_impl', 'uvicorn.lifespan.on'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter','PyQt5','PyQt6','PySide2','clr','pythonnet','webview.platforms.winforms',
              'webview.platforms.edgechromium','webview.platforms.cef','webview.platforms.gtk',
              'webview.platforms.cocoa','pytest','unittest','IPython','pandas','numpy'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[], name='PaintsDB', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, target_arch=None, codesign_identity=None,
          entitlements_file=None)
