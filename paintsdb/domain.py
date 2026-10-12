"""Shared validation and arithmetic, independent of the user interface."""
import ast
import math
import operator
import re
from datetime import date


class DomainError(ValueError):
    def __init__(self, message, field=None, code="validation"):
        super().__init__(message)
        self.field, self.code = field, code


def number(value, field, positive=False):
    if value is None or isinstance(value, bool) or value == "":
        raise DomainError("Укажите число", field)
    try:
        result = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        raise DomainError("Некорректное число", field) from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise DomainError("Число должно быть конечным и " + ("положительным" if positive else "неотрицательным"), field)
    return result


def month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) or value[:4] == "0000":
        raise DomainError("Укажите месяц в формате ГГГГ-ММ", "period")
    return value


def recipe_date(value=None):
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise DomainError("Некорректная дата изготовления", "manufactured_on") from None


def text(value, field, required=False, limit=2000):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise DomainError("Ожидается текст", field)
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise DomainError("Заполните поле" if not value else f"Не более {limit} символов", field)
    return value


def mass(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 250:
        raise DomainError("Укажите массу или выражение длиной до 250 символов", "mass_expression")
    source = expression.strip().lower()
    if not re.fullmatch(r"[0-9.\s+*/()\-кап]+", source):
        raise DomainError("Допустимы числа, + − * /, скобки и кап", "mass_expression")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def evaluate(node, depth=0):
        if depth > 30:
            raise ValueError()
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id == "кап":
            return 1.0
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](evaluate(node.left, depth + 1), evaluate(node.right, depth + 1))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return (1 if isinstance(node.op, ast.UAdd) else -1) * evaluate(node.operand, depth + 1)
        raise ValueError()

    try:
        result = evaluate(ast.parse(source, mode="eval").body)
        return number(result, "mass_expression", positive=True)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError, RecursionError):
        raise DomainError("Неверное выражение: результат должен быть положительным, деление на ноль запрещено", "mass_expression") from None


def price_values(data):
    period = month(data.get("period"))
    price = number(data.get("package_price"), "package_price")
    volume = number(data.get("volume_liters"), "volume_liters", positive=True)
    density = number(data.get("grams_per_liter"), "grams_per_liter", positive=True)
    net = number(volume * density, "net_grams", positive=True)
    unit = number(price / net, "price_per_gram")
    return dict(period=period, package_price=price, volume_liters=volume,
                grams_per_liter=density, net_grams=net, price_per_gram=unit)


def months_between(start, end):
    month(start); month(end)
    a = int(start[:4]) * 12 + int(start[5:]) - 1
    b = int(end[:4]) * 12 + int(end[5:]) - 1
    if b < a or b - a > 239:
        raise DomainError("Диапазон должен содержать от 1 до 240 месяцев", "period")
    return [f"{v // 12:04d}-{v % 12 + 1:02d}" for v in range(a, b + 1)]
