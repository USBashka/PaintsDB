"""Create only synthetic, reproducible demonstration data."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paintsdb.service import Service


def create_demo(path):
    service = Service()
    def call(operation, **kwargs):
        result = service.dispatch(operation, kwargs, service.context)
        if not result["ok"]:
            raise RuntimeError(result)
        return result["data"]
    call("create_database", path=str(path))
    ids = []
    for code, name, cost in [("A", "Белая база", 1000), ("B", "Синий пигмент", 2000), ("C", "Чёрный пигмент", 3000)]:
        component = call("save_component", code=code, name=name, aliases=[{"A":"белый","B":"синий","C":"чёрный"}[code]], price=dict(period="2026-07", package_price=cost, volume_liters=1, grams_per_liter=1000))
        ids.append(component["id"])
        component = call("save_price", component_id=component["id"], period="2026-09", package_price=cost*1.25 if code=="B" else cost, volume_liters=1, grams_per_liter=1000, revision=component["revision"])
        call("save_price", component_id=component["id"], period="2026-10", package_price=cost*1.1 if code=="A" else cost*1.25 if code=="B" else cost, volume_liters=1, grams_per_liter=1000, revision=component["revision"])
    for name, expressions, when in [("Основной состав", ["600","300","100"], "2026-07-15"), ("Вариант с меньшей долей синего", ["350","100","50"], "2026-08-20")]:
        call("save_recipe", name=name, color_code="DEMO-101", brand="Демонстрационная", manufactured_on=when,
             comment="Синтетический контрольный пример", lines=[dict(component_id=i,mass_expression=e) for i,e in zip(ids,expressions)])
    call("save_recipe", name="Проверка выражений", color_code="DEMO-202", manufactured_on="2026-10-12",
         lines=[dict(component_id=ids[0],mass_expression="20+15+кап"),dict(component_id=ids[1],mass_expression="(20+15)/2"),dict(component_id=ids[2],mass_expression="2*кап")])
    service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    create_demo(Path(parser.parse_args().path))
