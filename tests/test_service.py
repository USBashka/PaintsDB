import sqlite3
from pathlib import Path
import pytest
from paintsdb.service import Service


@pytest.fixture
def service(tmp_path):
    s=Service()
    assert s.dispatch("create_database",{"path":str(tmp_path/"test.paintsdb")})["ok"]
    yield s
    s.close()


def call(s, operation, **args):
    r=s.dispatch(operation,args,s.context)
    assert r["ok"], r
    return r["data"]


def component(s, code="A", cost=1000, period="2026-07"):
    return call(s,"save_component",code=code,name="Компонент "+code,aliases=["алиас"],price=dict(period=period,package_price=cost,volume_liters=1,grams_per_liter=1000))


def setup_recipe(s):
    cs=[component(s,c,p) for c,p in zip("ABC",[1000,2000,3000])]
    r=call(s,"save_recipe",color_code="101",manufactured_on="2026-07-15",lines=[dict(component_id=c["id"],mass_expression=e) for c,e in zip(cs,["600","300","100"])])
    return cs,r


def test_control_example_snapshot_history_and_comparison(service):
    s=service;cs,r=setup_recipe(s)
    assert r["snapshot_total"]==1500
    assert call(s,"calculate",lines=r["lines"],period="2026-08",target_mass=500)["total"]==750
    second=call(s,"save_recipe",color_code="101",manufactured_on="2026-08-20",lines=[dict(component_id=c["id"],mass_expression=e) for c,e in zip(cs,["350","100","50"])])
    call(s,"save_price",component_id=cs[1]["id"],period="2026-09",package_price=2500,volume_liters=1,grams_per_liter=1000,revision=cs[1]["revision"])
    current=call(s,"get_recipe",id=r["id"],period="2026-09")
    assert current["calculation"]["total"]==1650
    assert current["snapshot_total"]==1500
    h=call(s,"cost_history",ids=[r["id"],second["id"]],start="2026-06",end="2026-09")
    assert [v["total"] for v in h["series"][0]["values"]]==[None,1500,1500,1650]
    assert h["series"][0]["values"][2]["lines"][0]["price_period"]=="2026-07"
    comp=call(s,"compare_recipes",ids=[r["id"],second["id"]],period="2026-09")
    assert [v["calculation"]["total"] for v in comp]==[1650,1500]
    assert [v["snapshot_mass"] for v in comp]==[1000,500]
    assert call(s,"get_recipe",id=second["id"])["snapshot_mass"]==500


def test_optional_fields_and_expression_persistence(service):
    c=component(service)
    r=call(service,"save_recipe",lines=[dict(component_id=c["id"],mass_expression="20+15+кап")])
    assert r["name"]==r["color_code"]==r["vehicle"]==r["comment"]==""
    path=service.path
    call(service,"open_database",path=str(path))
    r=call(service,"get_recipe",id=r["id"])
    assert r["lines"][0]["mass_expression"]=="20+15+кап"
    assert r["lines"][0]["mass_grams"]==36
    assert call(service,"list_components",query="АЛИАС")[0]["id"]==c["id"]


def test_metadata_edit_keeps_snapshot_and_composition_edit_refreshes(service):
    cs,r=setup_recipe(service)
    call(service,"save_price",component_id=cs[0]["id"],period="2026-07",package_price=2000,volume_liters=1,grams_per_liter=1000,revision=cs[0]["revision"])
    r=call(service,"save_recipe",id=r["id"],revision=r["revision"],name="Правка имени",manufactured_on=r["manufactured_on"],lines=r["lines"])
    assert r["snapshot_total"]==1500
    r["lines"][0]["mass_expression"]="300"
    r=call(service,"save_recipe",id=r["id"],revision=r["revision"],manufactured_on=r["manufactured_on"],lines=r["lines"])
    assert r["snapshot_total"]==1500
    assert r["snapshot_mass"]==700
    assert r["lines"][0]["snapshot_price"]==2


def test_missing_prices_future_and_zero(service):
    c=component(service,cost=0)
    lines=[dict(component_id=c["id"],mass_expression="10")]
    assert call(service,"calculate",lines=lines,period="2026-07")["total"]==0
    assert call(service,"calculate",lines=lines,period="2026-06")["total"] is None
    error=service.dispatch("save_recipe",dict(lines=lines,manufactured_on="2026-06-01"),service.context)
    assert error["error"]["code"]=="missing_price"
    assert call(service,"list_recipes")==[]


def test_delete_restrict_and_independent_color(service):
    cs,r=setup_recipe(service)
    other=call(service,"save_recipe",color_code="101",lines=r["lines"])
    assert service.dispatch("delete_component",dict(id=cs[0]["id"],revision=1),service.context)["error"]["code"]=="in_use"
    call(service,"delete_recipe",id=r["id"],revision=r["revision"])
    assert call(service,"get_recipe",id=other["id"])["id"]==other["id"]


def test_stale_database_and_record(service,tmp_path):
    c=component(service);old=service.context
    call(service,"create_database",path=str(tmp_path/"second.paintsdb"))
    assert service.dispatch("save_component",dict(code="B",name="B"),old)["error"]["code"]=="database_changed"
    c=component(service)
    call(service,"save_component",id=c["id"],revision=c["revision"],code="A",name="Новое имя")
    assert service.dispatch("delete_component",dict(id=c["id"],revision=c["revision"]),service.context)["error"]["code"]=="conflict"


def test_backup_and_invalid_open(service,tmp_path):
    _,r=setup_recipe(service)
    copy=tmp_path/"backup.paintsdb"
    call(service,"backup_database",path=str(copy))
    invalid=tmp_path/"broken.db";invalid.write_bytes(b"not a database")
    context=service.context
    assert not service.dispatch("open_database",dict(path=str(invalid)),context)["ok"]
    assert service.context==context
    call(service,"open_database",path=str(copy))
    assert call(service,"get_recipe",id=r["id"])["snapshot_total"]==1500
    assert not service.dispatch("backup_database",dict(path=str(copy)),service.context)["ok"]


def test_alias_ambiguity_exact_ranking_and_unicode(service):
    a=component(service,"007");b=component(service,"b")
    result=call(service,"list_components",query="АЛИАС")
    assert len(result)==2
    assert call(service,"list_components",query="007")[0]["code"]=="007"
    assert a["id"]!=b["id"]


def test_invalid_recipe_transaction_and_notifications(service):
    cs,r=setup_recipe(service)
    result=service.dispatch("save_recipe",dict(id=r["id"],revision=r["revision"],lines=[dict(component_id=9999,mass_expression="10")]),service.context,"mcp")
    assert not result["ok"]
    assert call(service,"get_recipe",id=r["id"])["snapshot_total"]==1500
    result=service.dispatch("delete_recipe",dict(id=r["id"],revision=r["revision"]),service.context,"mcp")
    assert result["ok"]
    last=call(service,"events")["items"][-1]
    assert last["source"]=="mcp" and last["label"].startswith("101")


def test_no_database():
    s=Service()
    assert s.dispatch("list_components")["error"]["code"]=="no_database"
