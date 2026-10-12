"""Authenticated loopback MCP server sharing the desktop Service instance."""
import inspect
import json
import secrets
import socket
import threading
import time
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .service import OPERATIONS


DESCRIPTIONS = {
    "status": "Текущий открытый файл, database_id и context. Получите context перед вызовами. После смены базы старый context недействителен.",
    "create_database": "Создать новую SQLite-базу без перезаписи существующего файла и открыть её в приложении.",
    "open_database": "Открыть существующую базу PaintsDB в интерфейсе. Некорректный файл не заменяет текущую базу.",
    "save_component": "Создать или исправить компонент, алиасы и необязательную месячную цену. Для изменения нужны id и revision. Алиасы — список строк; price содержит period, package_price, volume_liters, grams_per_liter.",
    "save_recipe": "Сохранить изготовление. Все реквизиты необязательны; дата по умолчанию сегодня. lines: [{component_id: int, mass_expression: str}]. Передавайте исходное выражение, включая кап=1г. Для правки обязательны id и revision. Полный исходный расчёт обязателен; неизвестные компоненты и отсутствующие цены дают ошибку.",
    "calculate": "Рассчитать lines [{component_id, mass_expression}] по выбранному месяцу period. target_mass — необязательная масса партии. Нет цены: total=null и список missing, без частичной суммы.",
    "apply_import": "Атомарно применить явно выбранные ключи selected_rows из preview_import. Повторы кода: выбрать ровно одну строку. Неполный прайс создаёт только компонент; чужие алиасы и рецепты сохраняются.",
    "preview_import": "Проверить XLSX: вернуть token, строки с key, errors, warnings, selected. Ничего не записывает. period необязателен для переопределения месяца.",
    "compare_recipes": "Сравнить от 1 до 12 рецептов одного цвета на 1000 г по ценам period. Не изменяет рецепты.",
    "cost_history": "История стоимости ids в диапазоне start/end ГГГГ-ММ. mode: per_kg или batch. Для нескольких рецептов допускается только per_kg и один цвет.",
    "list_recipes": "Поиск по реквизитам, фильтры color_code и manufactured_month. sort: created_at, updated_at, manufactured_on, color_code, name, mass_grams, cost. cost_mode: selected, snapshot, current, per_kg.",
    "list_components": "Поиск query по коду, названию и алиасам; точные совпадения кода/алиаса выше. sort: code, name, price_per_gram, updated_at. При неоднозначном совпадении предложить выбор, не подставлять автоматически.",
    "delete_component": "Удалить компонент по id и revision. Используемый в рецептах компонент удалить нельзя.",
    "delete_recipe": "Удалить только указанный рецепт по id и revision. Другие варианты цвета сохраняются.",
    "save_price": "Записать или обновить ценовые параметры component_id за period; нужна актуальная revision компонента. Исходные снимки рецептов не меняются.",
    "delete_price": "Удалить месячную цену; нужна revision компонента. Снимки рецептов сохраняются, пересчёт может стать недоступен.",
    "export_components": "Выгрузить компоненты и использованные месячные ценовые параметры в XLSX. Существующий файл не перезаписывается.",
    "backup_database": "Создать согласованную резервную копию SQLite по новому пути path. Для восстановления открыть копию через open_database.",
    "events": "Изменения интерфейса и MCP после номера after; содержит имена удалённых записей.",
    "get_recipe": "Прочитать рецепт с исходными выражениями, снимком, выбранным и текущим расчётами. period необязателен.",
    "get_component": "Прочитать компонент, алиасы, revision и полный месячный прайс.",
    "evaluate_mass": "Безопасно вычислить выражение массы: числа, + - * /, скобки, кап. Без исполнения программного кода.",
}


def build_mcp(service):
    mcp = FastMCP("PaintsDB", host="127.0.0.1", stateless_http=True, json_response=True,
                  instructions="Используйте paints_status и сохраняйте context для всех операций. При ошибке database_changed заново согласуйте базу. Не выдумывайте неизвестные реквизиты или коды. Все описательные поля рецепта необязательны.")
    types = {"id": int, "component_id": int, "revision": int | None, "after": int,
             "descending": bool, "lines": list[dict], "ids": list[int], "selected_rows": list[str],
             "aliases": list[str] | None, "price": dict | None, "target_mass": float | None,
             "package_price": float, "volume_liters": float, "grams_per_liter": float}

    def register(operation):
        method = getattr(service, operation)
        params = [p.replace(annotation=types.get(p.name, str | None if p.default is None else str)) for p in inspect.signature(method).parameters.values()]
        guarded = operation not in ("status", "events", "evaluate_mass")
        if guarded:
            default = None if operation in ("open_database", "create_database") else inspect.Parameter.empty
            params.append(inspect.Parameter("context", inspect.Parameter.KEYWORD_ONLY, annotation=str | None, default=default))

        def call(**kwargs):
            context = kwargs.pop("context", None)
            response = service.dispatch(operation, kwargs, context, source="mcp")
            if not response["ok"]:
                raise ToolError(json.dumps(response["error"], ensure_ascii=False))
            return response

        call.__name__ = "paints_" + operation
        call.__doc__ = DESCRIPTIONS[operation]
        call.__signature__ = inspect.Signature(params, return_annotation=dict[str, Any])
        call.__annotations__ = {p.name: p.annotation for p in params}
        call.__annotations__["return"] = dict[str, Any]
        mcp.tool()(call)

    for operation in OPERATIONS:
        register(operation)
    return mcp


class BearerOnly:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode("latin1")
            if not secrets.compare_digest(auth, "Bearer " + self.token) or b"origin" in headers:
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)


class MCPServer:
    def __init__(self, service, port=47831, token=None):
        self.token = token or secrets.token_urlsafe(32)
        self.mcp = build_mcp(service)
        self.socket = socket.socket()
        try:
            self.socket.bind(("127.0.0.1", port))
        except OSError:
            self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        config = uvicorn.Config(BearerOnly(self.mcp.streamable_http_app(), self.token), log_level="warning", log_config=None, access_log=False)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Не удалось запустить локальный MCP")
            time.sleep(0.02)
        return self

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=4)
        self.socket.close()
