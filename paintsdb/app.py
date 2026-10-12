import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .service import Service


class Bridge:
    def __init__(self, service, server, config_path):
        self._service, self._server, self._config_path = service, server, config_path
        self._window = None

    def request(self, operation, args=None, context=None):
        result = self._service.dispatch(operation, args, context)
        if result["ok"] and operation in ("create_database", "open_database"):
            self._config_path.write_text(json.dumps({"last_database": str(self._service.path), "mcp_token": self._server.token}, ensure_ascii=False), encoding="utf-8")
        return result

    def choose_file(self, purpose):
        import webview
        settings = {
            "open": (webview.FileDialog.OPEN, "Открыть базу", ("База PaintsDB (*.paintsdb;*.sqlite;*.db)", "Все файлы (*.*)"), ""),
            "create": (webview.FileDialog.SAVE, "Создать базу", ("База PaintsDB (*.paintsdb)",), "Краски.paintsdb"),
            "backup": (webview.FileDialog.SAVE, "Сохранить резервную копию", ("База PaintsDB (*.paintsdb)",), "Краски-копия.paintsdb"),
            "import": (webview.FileDialog.OPEN, "Импорт компонентов", ("Книга Excel (*.xlsx)",), ""),
            "export": (webview.FileDialog.SAVE, "Экспорт компонентов", ("Книга Excel (*.xlsx)",), "Компоненты.xlsx"),
        }
        if purpose not in settings:
            return None
        kind, title, filters, filename = settings[purpose]
        result = self._window.create_file_dialog(kind, allow_multiple=False, file_types=filters, save_filename=filename)
        if not result:
            return None
        path = result[0] if isinstance(result, (tuple, list)) else result
        if purpose in ("create", "backup") and not Path(path).suffix:
            path += ".paintsdb"
        if purpose == "export" and not Path(path).suffix:
            path += ".xlsx"
        return path

    def mcp_settings(self):
        return {"url": self._server.url, "token": self._server.token}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database")
    parser.add_argument("--data-dir")
    parser.add_argument("--smoke", metavar="RESULT_JSON")
    args = parser.parse_args()
    base = Path(args.data_dir or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PaintsDB")
    base.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=base / "paintsdb.log", level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    config_path = base / "settings.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    service = Service()
    database = args.database or config.get("last_database")
    startup_error = None
    if database:
        result = service.dispatch("open_database", {"path": database})
        if not result["ok"]:
            startup_error = result["error"]["message"]
    from .mcp_server import MCPServer
    server = MCPServer(service, token=config.get("mcp_token")).start()
    config["mcp_token"] = server.token
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    bridge = Bridge(service, server, config_path)
    os.environ["QT_API"] = "pyside6"
    from PySide6.QtCore import QLocale, QObject, Signal, Slot
    QLocale.setDefault(QLocale("ru_RU"))
    import webview
    webview.settings["ALLOW_DOWNLOADS"] = False
    window = webview.create_window("PaintsDB", url=str(Path(__file__).with_name("ui") / "index.html"), js_api=bridge,
                                   width=1280, height=820, min_size=(900, 620), background_color="#f3f3f3")
    bridge._window = window

    class SmokeCapture(QObject):
        requested = Signal()

        def __init__(self):
            super().__init__()
            import threading
            self.done = threading.Event()
            self.requested.connect(self.capture)

        @Slot()
        def capture(self):
            self.ok = window.native.grab().save(str(Path(args.smoke).with_suffix(".png")))
            self.done.set()

    capture = SmokeCapture() if args.smoke else None

    def ready():
        if startup_error:
            window.evaluate_js("window.startupError=" + json.dumps(startup_error))
        if args.smoke:
            import time
            for _ in range(100):
                time.sleep(0.1)
                if window.evaluate_js("Boolean(window.appReady)"):
                    break
            result = window.evaluate_js("JSON.stringify({ready:window.appReady,title:document.title,body:document.body.innerText,errors:window.uiErrors||[]})")
            capture.requested.emit()
            if not capture.done.wait(10) or not capture.ok:
                logging.error("Smoke screenshot failed")
            Path(args.smoke).write_text(result, encoding="utf-8")
            window.destroy()

    close_state = {"approved": False, "pending": False}

    def closing():
        if close_state["approved"]:
            return True
        if not close_state["pending"]:
            close_state["pending"] = True

            def decide():
                try:
                    dirty = window.evaluate_js("Boolean(window.dirty)")
                    if not dirty or window.create_confirmation_dialog("PaintsDB", "Закрыть приложение без сохранения изменений?"):
                        close_state["approved"] = True
                        window.destroy()
                except Exception:
                    logging.exception("Could not verify unsaved changes on close")
                finally:
                    close_state["pending"] = False

            import threading
            threading.Thread(target=decide, daemon=True).start()
        # Qt must return to its event loop before evaluating JavaScript or showing a dialog.
        return False

    window.events.closing += closing
    try:
        webview.start(ready, gui="qt", private_mode=True, storage_path=str(base / "webview"))
    finally:
        server.stop()
        service.close()


if __name__ == "__main__":
    main()
