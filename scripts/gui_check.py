"""Integration test inside the real Qt WebEngine window; no external browser mocks."""
import json
import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['QT_API']='pyside6'
from PySide6.QtCore import QObject, Signal, Slot, QLocale
QLocale.setDefault(QLocale('ru_RU'))
import webview
from paintsdb.app import Bridge
from paintsdb.service import Service
from paintsdb.mcp_server import MCPServer
from create_demo import create_demo

folder=ROOT/'.qa'/('gui-'+str(int(time.time())))
folder.mkdir(parents=True)
create_demo(folder/'demo.paintsdb')
from openpyxl import Workbook
from paintsdb.excel import HEADERS
book=Workbook();sheet=book.active;sheet.append(HEADERS)
for row in [('A','Белая база','2026-10',1100,1,1000),('D','Вариант 1','2026-10',100,1,1000),('D','Вариант 2','2026-10',200,1,1000),('E','Без цены','2026-10',None,1,None),('F','','2026-10',100,1,1000)]:
    sheet.append(row)
book.save(folder/'input.xlsx')
service=Service()
result=service.dispatch('open_database',dict(path=str(folder/'demo.paintsdb')))
assert result['ok'],result
server=MCPServer(service,port=0).start()


class Capture(QObject):
    signal=Signal(str)
    def __init__(self):
        super().__init__()
        self.done=threading.Event()
        self.signal.connect(self.capture)

    @Slot(str)
    def capture(self,name):
        self.ok=window.native.grab().save(str(folder/(name+'.png')))
        self.done.set()


capture=Capture()


class TestBridge(Bridge):
    def choose_file(self,purpose):
        if purpose=='import':return str(folder/'input.xlsx')
        return super().choose_file(purpose)

    def simulate_mcp_edit(self,identity):
        recipe=self._service.dispatch('get_recipe',dict(id=identity),self._service.context)['data']
        return self._service.dispatch('save_recipe',dict(id=identity,revision=recipe['revision'],name='Изменено через MCP',color_code=recipe['color_code'],manufactured_on=recipe['manufactured_on'],lines=recipe['lines']),self._service.context,'mcp')

    def checkpoint(self,name):
        capture.done.clear();capture.signal.emit(name)
        if not capture.done.wait(10) or not capture.ok:
            raise RuntimeError('Screenshot failed: '+name)
        return True


bridge=TestBridge(service,server,folder/'settings.json')
parser=argparse.ArgumentParser()
parser.add_argument('--height',type=int,default=850)
options=parser.parse_args()
window=webview.create_window('PaintsDB — проверка',url=str(ROOT/'paintsdb/ui/index.html'),js_api=bridge,width=1280,height=options.height,min_size=(900,620))
bridge._window=window


def check():
    try:
        for _ in range(200):
            if window.evaluate_js('Boolean(window.appReady)'):break
            time.sleep(.1)
        window.evaluate_js((ROOT/'tests/gui_scenario.js').read_text(encoding='utf-8'))
        for _ in range(900):
            if window.evaluate_js('Boolean(window.qaResult)'):break
            time.sleep(.1)
        result=window.evaluate_js('JSON.stringify(window.qaResult||{ok:false,error:"GUI timeout"})')
        (folder/'result.json').write_text(result,encoding='utf-8')
    except Exception as exc:
        (folder/'result.json').write_text(json.dumps(dict(ok=False,error=str(exc))),encoding='utf-8')
    finally:
        window.evaluate_js('window.dirty=false')
        window.destroy()


try:
    webview.start(check,gui='qt',private_mode=True,storage_path=str(folder/'webview'))
finally:
    server.stop();service.close()
    print(folder)
    if (folder/'result.json').exists():print((folder/'result.json').read_text(encoding='utf-8'))
