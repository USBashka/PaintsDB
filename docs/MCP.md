# Подключение внешнего ИИ

Запустите PaintsDB и откройте базу. В меню **Файл → Подключение MCP** доступны адрес и Bearer-токен. Сервер использует Streamable HTTP и работает только на `127.0.0.1`. По умолчанию порт — 47831; если он занят, фактический порт виден в окне подключения. Запросы с заголовком Origin отклоняются. Токен остаётся локальным.

Пример конфигурации клиента с HTTP-подключениями:

```json
{
  "mcpServers": {
    "paintsdb": {
      "url": "http://127.0.0.1:47831/mcp",
      "headers": { "Authorization": "Bearer <токен из приложения>" }
    }
  }
}
```

Конкретное имя раздела зависит от MCP-клиента. Приложение должно оставаться открытым. Использован официальный Python SDK MCP 1.30.0. Все 22 операции доступны через инструменты `paints_*`; схемы и описания возвращаются `tools/list`.

Сначала вызовите `paints_status`. Каждое обращение к данным требует возвращённый `context`. Это идентификатор текущего открытия файла, а не постоянный database_id. После переключения базы старый context отклоняется. Создание и открытие базы также требуют текущий context, если база уже открыта.

Инструменты: `list_components`, `get_component`, `save_component`, `save_price`, `delete_price`, `delete_component`, `evaluate_mass`, `calculate`, `list_recipes`, `get_recipe`, `save_recipe`, `delete_recipe`, `compare_recipes`, `cost_history`, `preview_import`, `apply_import`, `export_components`, `backup_database`, `create_database`, `open_database`, `status`, `events` — с префиксом `paints_`.

## Пример рецепта

```json
{
  "context": "<из paints_status>",
  "color_code": "DEMO-101",
  "manufactured_on": "2026-08-20",
  "lines": [{ "component_id": 1, "mass_expression": "20+15+кап" }]
}
```

Реквизиты необязательны. Отсутствующая дата означает текущий день. Для исправления передаются id и revision из свежего чтения. Запись без полной цены на дату изготовления отклоняется. Изменения применяются сразу и отражаются в уведомлении интерфейса. Неизвестный код не подменяется похожим.

Ответ: `{ok:true,data:...}`. Ошибка MCP имеет `isError=true` и JSON с code, message, field. Коды: `no_database`, `database_changed`, `validation`, `not_found`, `missing_price`, `conflict`, `in_use`, `stale_import`, `operation_failed`.

Для ввода по фотографиям подготовлен `skills/paintsdb-recipes/SKILL.md`. Он не устанавливается и не меняет конфигурацию ИИ автоматически.
