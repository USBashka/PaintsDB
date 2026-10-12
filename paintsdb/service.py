"""One transactional application service shared by the desktop bridge and MCP."""
import json
import logging
import sqlite3
import threading
import uuid
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path

from .domain import DomainError, mass, month, months_between, number, price_values, recipe_date, text


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Service:
    def __init__(self):
        self.lock = threading.RLock()
        self.db = None
        self.path = None
        self.context = None
        self.db_id = None
        self.event_log = deque(maxlen=200)
        self.sequence = 0
        self.previews = {}

    def close(self):
        with self.lock:
            if self.db:
                self.db.close()
            self.db = None

    def dispatch(self, operation, args=None, context=None, source="ui"):
        with self.lock:
            try:
                if operation not in OPERATIONS:
                    raise DomainError("Неизвестная операция", code="unknown_operation")
                args = dict(args or {})
                if operation not in ("status", "open_database", "create_database", "events", "evaluate_mass"):
                    self.require_db(context)
                elif operation in ("open_database", "create_database") and self.db and context != self.context:
                    raise DomainError("База была переключена. Обновите состояние", code="database_changed")
                self.source = source
                result = getattr(self, operation)(**args)
                return {"ok": True, "data": result}
            except DomainError as exc:
                return {"ok": False, "error": {"code": exc.code, "message": str(exc), "field": exc.field}}
            except (sqlite3.Error, OSError, TypeError, ValueError, KeyError) as exc:
                logging.exception("Operation %s failed", operation)
                return {"ok": False, "error": {"code": "operation_failed", "message": str(exc)}}

    def require_db(self, context):
        if not self.db:
            raise DomainError("Откройте или создайте базу данных", code="no_database")
        if context != self.context:
            raise DomainError("База была переключена. Обновите состояние и повторите операцию", code="database_changed")

    def status(self):
        return {"path": str(self.path) if self.path else None, "context": self.context,
                "database_id": self.db_id, "sequence": self.sequence, "today": date.today().isoformat()}

    def events(self, after=0):
        return {"items": [e for e in self.event_log if e["sequence"] > after], **self.status()}

    def event(self, action, entity, ids, label=""):
        self.sequence += 1
        item = dict(sequence=self.sequence, action=action, entity=entity, ids=ids,
                    label=label, count=len(ids), source=self.source, context=self.context, time=now())
        self.event_log.append(item)

    def create_database(self, path):
        target = Path(path).expanduser().resolve()
        if target.exists():
            raise DomainError("Файл уже существует. Выберите другое имя", "path")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwriting a concurrently created file.
        with target.open("xb"):
            pass
        db = sqlite3.connect(target)
        try:
            db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            db.execute("INSERT INTO metadata VALUES ('database_id',?)", (str(uuid.uuid4()),))
            db.commit()
        finally:
            db.close()
        return self.open_database(str(target))

    def open_database(self, path):
        target = Path(path).expanduser().resolve(strict=True)
        db = sqlite3.connect(target.as_uri() + "?mode=rw", uri=True, check_same_thread=False, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != 1:
                raise DomainError("Этот файл не является поддерживаемой базой PaintsDB", "path")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise DomainError("База данных повреждена", "path")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise DomainError("В базе нарушены связи между записями", "path")
            for table in ("components", "aliases", "prices", "recipes", "recipe_lines"):
                db.execute(f"SELECT * FROM {table} LIMIT 0")
            identity = db.execute("SELECT value FROM metadata WHERE key='database_id'").fetchone()
            if not identity:
                raise DomainError("Отсутствует идентификатор базы", "path")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
        except Exception:
            db.close()
            raise
        if self.db:
            self.db.close()
        self.db, self.path, self.db_id = db, target, identity[0]
        self.context = str(uuid.uuid4())
        self.previews.clear()
        self.event("Открыта база", "database", [], target.name)
        return self.status()

    def backup_database(self, path):
        target = Path(path).expanduser().resolve()
        if target.exists():
            raise DomainError("Файл уже существует. Выберите другое имя", "path")
        with target.open("xb"):
            pass
        backup = sqlite3.connect(target)
        try:
            self.db.backup(backup)
        finally:
            backup.close()
        self.event("Создана резервная копия", "database", [], target.name)
        return {"path": str(target)}

    def evaluate_mass(self, expression):
        return {"mass_expression": expression, "mass_grams": mass(expression)}

    def row(self, table, identity):
        result = self.db.execute(f"SELECT * FROM {table} WHERE id=?", (identity,)).fetchone()
        if not result:
            raise DomainError("Запись не найдена", "id", "not_found")
        return dict(result)

    def check_revision(self, record, revision):
        if revision != record["revision"]:
            raise DomainError("Запись уже изменена. Откройте её заново, чтобы сохранить правки", code="conflict")

    def price(self, component_id, period):
        row = self.db.execute("SELECT * FROM prices WHERE component_id=? AND period<=? ORDER BY period DESC LIMIT 1", (component_id, period)).fetchone()
        return {**dict(row), **price_values(dict(row))} if row else None

    def list_components(self, query="", period=None, sort="code", descending=False):
        period = month(period or date.today().strftime("%Y-%m"))
        query = text(query, "query").casefold()
        items = []
        for row in self.db.execute("SELECT * FROM components"):
            item = dict(row)
            item["aliases"] = [r[0] for r in self.db.execute("SELECT value FROM aliases WHERE component_id=? ORDER BY normalized", (item["id"],))]
            values = [item["code"], item["name"], *item["aliases"]]
            if query and not any(query in v.casefold() for v in values):
                continue
            item["price"] = self.price(item["id"], period)
            item["price_per_gram"] = item["price"]["price_per_gram"] if item["price"] else None
            item["exact"] = query in [v.casefold() for v in [item["code"], *item["aliases"]]]
            items.append(item)
        if sort not in ("code", "name", "price_per_gram", "updated_at"):
            raise DomainError("Неизвестная сортировка")
        items = self.sorted_items(items, sort, descending)
        if query:
            items.sort(key=lambda r: not r["exact"])
        return items

    @staticmethod
    def sorted_items(items, field, descending):
        available = [r for r in items if r.get(field) is not None]
        missing = [r for r in items if r.get(field) is None]
        return sorted(available, key=lambda r: r[field].casefold() if isinstance(r[field], str) else r[field], reverse=descending) + missing

    def get_component(self, id):
        result = self.row("components", id)
        result["aliases"] = [r[0] for r in self.db.execute("SELECT value FROM aliases WHERE component_id=?", (id,))]
        result["prices"] = [{**dict(r), **price_values(dict(r))} for r in self.db.execute("SELECT * FROM prices WHERE component_id=? ORDER BY period DESC", (id,))]
        return result

    def save_component(self, code, name, aliases=None, id=None, revision=None, price=None):
        code, name = text(code, "code", True, 100), text(name, "name", True, 500)
        if aliases is not None and not isinstance(aliases, list):
            raise DomainError("Алиасы должны быть списком", "aliases")
        clean_aliases = {text(a, "aliases", True, 100).casefold(): a.strip() for a in (aliases or [])}
        values = price_values(price) if price else None
        stamp = now()
        with self.db:
            if id is not None:
                old = self.row("components", id)
                self.check_revision(old, revision)
                self.db.execute("UPDATE components SET code=?,name=?,updated_at=?,revision=revision+1 WHERE id=?", (code, name, stamp, id))
            else:
                id = self.db.execute("INSERT INTO components(code,name,created_at,updated_at) VALUES(?,?,?,?)", (code, name, stamp, stamp)).lastrowid
            self.db.execute("DELETE FROM aliases WHERE component_id=?", (id,))
            self.db.executemany("INSERT INTO aliases VALUES(?,?,?)", [(id, value, key) for key, value in clean_aliases.items()])
            if values:
                self._put_price(id, values)
        self.event("Изменён компонент" if revision else "Добавлен компонент", "component", [id], f"{code} · {name}")
        return self.get_component(id)

    def _put_price(self, component_id, values):
        self.db.execute("""INSERT INTO prices VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(component_id,period) DO UPDATE SET package_price=excluded.package_price,
            volume_liters=excluded.volume_liters,grams_per_liter=excluded.grams_per_liter,
            source=excluded.source,updated_at=excluded.updated_at""",
            (component_id, values["period"], values["package_price"], values["volume_liters"], values["grams_per_liter"], self.source, now()))

    def save_price(self, component_id, period, package_price, volume_liters, grams_per_liter, revision):
        component = self.row("components", component_id)
        self.check_revision(component, revision)
        values = price_values(locals())
        with self.db:
            self._put_price(component_id, values)
            self.db.execute("UPDATE components SET updated_at=?,revision=revision+1 WHERE id=?", (now(), component_id))
        self.event("Изменена цена", "component", [component_id], component["code"])
        return self.get_component(component_id)

    def delete_price(self, component_id, period, revision):
        component = self.row("components", component_id)
        self.check_revision(component, revision)
        month(period)
        with self.db:
            self.db.execute("DELETE FROM prices WHERE component_id=? AND period=?", (component_id, period))
            self.db.execute("UPDATE components SET updated_at=?,revision=revision+1 WHERE id=?", (now(), component_id))
        self.event("Удалена цена", "component", [component_id], component["code"] + " · " + period)
        return self.get_component(component_id)

    def delete_component(self, id, revision):
        component = self.row("components", id)
        self.check_revision(component, revision)
        if self.db.execute("SELECT 1 FROM recipe_lines WHERE component_id=? LIMIT 1", (id,)).fetchone():
            raise DomainError("Компонент используется в рецептах и не может быть удалён", code="in_use")
        with self.db:
            self.db.execute("DELETE FROM components WHERE id=?", (id,))
        self.event("Удалён компонент", "component", [id], component["code"] + " · " + component["name"])
        return {"id": id}

    def calculate(self, lines, period, target_mass=None):
        month(period)
        if not isinstance(lines, list) or not 1 <= len(lines) <= 500:
            raise DomainError("Добавьте от 1 до 500 компонентов", "lines")
        result, missing = [], []
        for i, line in enumerate(lines):
            try:
                component = self.row("components", line.get("component_id"))
                expression = line.get("mass_expression", "")
                grams = mass(expression)
            except DomainError as exc:
                exc.field = f"lines.{i}.{exc.field or 'component_id'}"
                raise
            p = self.price(component["id"], period)
            if p is None:
                missing.append(component["code"])
            result.append(dict(component_id=component["id"], code=component["code"], name=component["name"],
                               mass_expression=expression, mass_grams=grams,
                               price_per_gram=p["price_per_gram"] if p else None,
                               price_period=p["period"] if p else None))
        original_mass = number(sum(r["mass_grams"] for r in result), "mass", True)
        factor = number(target_mass, "target_mass", True) / original_mass if target_mass is not None else 1
        for item in result:
            item["share"] = item["mass_grams"] / original_mass
            item["mass_grams"] *= factor
            item["cost"] = number(item["mass_grams"] * item["price_per_gram"], "cost") if item["price_per_gram"] is not None else None
        total = number(sum(r["cost"] for r in result), "total") if not missing else None
        total_mass = number(original_mass * factor, "mass", True)
        return dict(lines=result, period=period, original_mass=original_mass, mass_grams=total_mass,
                    total=total, per_kg=number(total / total_mass * 1000, "per_kg") if total is not None else None,
                    missing=sorted(set(missing)))

    def save_recipe(self, lines, name="", color_code="", brand="", vehicle="", work_order="", comment="", manufactured_on=None, id=None, revision=None):
        fields = {k: text(v, k) for k, v in dict(name=name, color_code=color_code, brand=brand, vehicle=vehicle, work_order=work_order, comment=comment).items()}
        fields["manufactured_on"] = recipe_date(manufactured_on)
        old = self.get_recipe(id) if id is not None else None
        if old:
            self.check_revision(old, revision)
        normalized = [(r.get("component_id"), r.get("mass_expression", "")) for r in lines]
        changed = not old or fields["manufactured_on"] != old["manufactured_on"] or normalized != [(r["component_id"], r["mass_expression"]) for r in old["lines"]]
        calc = self.calculate(lines, fields["manufactured_on"][:7]) if changed else None
        if calc and calc["missing"]:
            raise DomainError("Нет цены на дату изготовления: " + ", ".join(calc["missing"]), "lines", "missing_price")
        stamp = now()
        with self.db:
            if old:
                self.db.execute("UPDATE recipes SET " + ",".join(f"{k}=?" for k in fields) + ",updated_at=?,revision=revision+1 WHERE id=?", (*fields.values(), stamp, id))
            else:
                id = self.db.execute("INSERT INTO recipes(" + ",".join(fields) + ",created_at,updated_at,source,snapshot_total,snapshot_mass) VALUES(" + ",".join("?" for _ in range(len(fields) + 5)) + ")", (*fields.values(), stamp, stamp, self.source, calc["total"], calc["mass_grams"])).lastrowid
            if changed:
                self.db.execute("UPDATE recipes SET snapshot_total=?,snapshot_mass=? WHERE id=?", (calc["total"], calc["mass_grams"], id))
                self.db.execute("DELETE FROM recipe_lines WHERE recipe_id=?", (id,))
                self.db.executemany("INSERT INTO recipe_lines VALUES(?,?,?,?,?,?,?)", [(id, i, r["component_id"], r["mass_expression"], r["mass_grams"], r["price_per_gram"], r["price_period"]) for i, r in enumerate(calc["lines"])])
        self.event("Изменён рецепт" if old else "Добавлен рецепт", "recipe", [id], fields["color_code"] + " · " + (fields["name"] or f"Рецепт {id}"))
        return self.get_recipe(id)

    def get_recipe(self, id, period=None):
        result = self.row("recipes", id)
        result["lines"] = [dict(r) for r in self.db.execute("SELECT l.*,c.code,c.name FROM recipe_lines l JOIN components c ON c.id=l.component_id WHERE recipe_id=? ORDER BY position", (id,))]
        result["calculation"] = self.calculate(result["lines"], month(period or date.today().strftime("%Y-%m")))
        result["current"] = self.calculate(result["lines"], date.today().strftime("%Y-%m"))
        return result

    def list_recipes(self, query="", color_code=None, manufactured_month=None, period=None, cost_mode="selected", sort="created_at", descending=True):
        period = month(period or date.today().strftime("%Y-%m"))
        if manufactured_month:
            month(manufactured_month)
        query = text(query, "query").casefold()
        if cost_mode not in ("selected", "snapshot", "current", "per_kg"):
            raise DomainError("Неизвестный режим стоимости")
        if sort not in ("created_at", "updated_at", "manufactured_on", "color_code", "name", "mass_grams", "cost"):
            raise DomainError("Неизвестная сортировка")
        items = []
        for row in self.db.execute("SELECT * FROM recipes"):
            r = dict(row)
            if color_code is not None and r["color_code"].casefold() != color_code.casefold():
                continue
            if manufactured_month and not r["manufactured_on"].startswith(manufactured_month):
                continue
            if query and not any(query in r[k].casefold() for k in ("name", "color_code", "brand", "vehicle", "work_order", "comment")):
                continue
            full = self.get_recipe(r["id"], period)
            r["mass_grams"] = r["snapshot_mass"]
            r["cost"] = {"selected": full["calculation"]["total"], "snapshot": r["snapshot_total"], "current": full["current"]["total"], "per_kg": full["calculation"]["per_kg"]}[cost_mode]
            r["missing"] = full["calculation"]["missing"]
            items.append(r)
        return self.sorted_items(items, sort, descending)

    def delete_recipe(self, id, revision):
        r = self.row("recipes", id)
        self.check_revision(r, revision)
        with self.db:
            self.db.execute("DELETE FROM recipes WHERE id=?", (id,))
        self.event("Удалён рецепт", "recipe", [id], r["color_code"] + " · " + (r["name"] or f"Рецепт {id}"))
        return {"id": id}

    def compare_recipes(self, ids, period):
        if not 1 <= len(ids) <= 12 or len(set(ids)) != len(ids):
            raise DomainError("Выберите от 1 до 12 разных рецептов")
        recipes = [self.get_recipe(i, period) for i in ids]
        if len({r["color_code"].casefold() for r in recipes}) > 1:
            raise DomainError("Для сравнения выберите рецепты одного цвета")
        return [{"id": r["id"], "name": r["name"], "color_code": r["color_code"], "manufactured_on": r["manufactured_on"], "snapshot_total": r["snapshot_total"], "snapshot_mass": r["snapshot_mass"], "calculation": self.calculate(r["lines"], period, 1000)} for r in recipes]

    def cost_history(self, ids, start, end, mode="per_kg"):
        periods = months_between(start, end)
        if mode not in ("per_kg", "batch") or not 1 <= len(ids) <= 12:
            raise DomainError("Неверные параметры графика")
        recipes = [self.get_recipe(i) for i in ids]
        if len(recipes) > 1 and (mode != "per_kg" or len({r["color_code"].casefold() for r in recipes}) != 1):
            raise DomainError("Сравнение выполняется для одного цвета на 1 кг")
        return {"periods": periods, "mode": mode, "series": [dict(id=r["id"], name=r["name"], manufactured_on=r["manufactured_on"], values=[self.calculate(r["lines"], p, 1000 if mode == "per_kg" else None) for p in periods]) for r in recipes]}

    def preview_import(self, path, period=None):
        from .excel import preview
        result = preview(path, period)
        token = str(uuid.uuid4())
        self.previews[token] = {"context": self.context, "result": result, "sequence": self.sequence}
        # Bound retained workbooks, including requests made by external clients.
        while len(self.previews) > 8:
            del self.previews[next(iter(self.previews))]
        return {"token": token, **result}

    def apply_import(self, token, selected_rows):
        pending = self.previews.get(token)
        if not pending or pending["context"] != self.context:
            raise DomainError("Повторите предварительную проверку файла", code="stale_import")
        if pending["sequence"] != self.sequence:
            raise DomainError("Данные изменились после проверки. Повторите проверку импорта", code="stale_import")
        selected = set(selected_rows)
        rows = [r for r in pending["result"]["rows"] if r["key"] in selected]
        if not rows or len(rows) != len(selected) or any(r["errors"] for r in rows):
            raise DomainError("Выберите строки без ошибок", "selected_rows")
        if len({r["code"] for r in rows}) != len(rows):
            raise DomainError("Выберите только одну строку каждого повторяющегося кода", "selected_rows")
        created = updated = 0
        ids = []
        with self.db:
            for r in rows:
                found = self.db.execute("SELECT id FROM components WHERE code=?", (r["code"],)).fetchone()
                stamp = now()
                if found:
                    identity = found[0]
                    self.db.execute("UPDATE components SET name=?,updated_at=?,revision=revision+1 WHERE id=?", (r["name"], stamp, identity))
                    updated += 1
                else:
                    identity = self.db.execute("INSERT INTO components(code,name,created_at,updated_at) VALUES(?,?,?,?)", (r["code"], r["name"], stamp, stamp)).lastrowid
                    created += 1
                if r["price"]:
                    self._put_price(identity, r["price"])
                ids.append(identity)
        del self.previews[token]
        self.event("Импортированы компоненты", "component", ids, pending["result"]["period"])
        return dict(created=created, updated=updated, period=pending["result"]["period"], ids=ids, without_price=sum(r["price"] is None for r in rows))

    def export_components(self, path, period):
        from .excel import export
        month(period)
        export(path, self.list_components(period=period), period)
        return {"path": str(Path(path).resolve()), "period": period}


OPERATIONS = ("status", "open_database", "create_database", "backup_database", "events", "evaluate_mass",
              "list_components", "get_component", "save_component", "save_price", "delete_price", "delete_component",
              "calculate", "save_recipe", "get_recipe", "list_recipes", "delete_recipe", "compare_recipes",
              "cost_history", "preview_import", "apply_import", "export_components")
