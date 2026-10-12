import pytest
from paintsdb.domain import DomainError, mass, month, price_values, months_between


@pytest.mark.parametrize("expression,expected", [("20+15+кап",36),("2*КАП",2),("(20+15)/2",17.5),(" 0.375 ",.375),("10-2*3",4),("+2",2)])
def test_mass(expression, expected):
    assert mass(expression) == expected


@pytest.mark.parametrize("expression", ["", "0", "-1", "1/0", "1+", "(1+2", "float('nan')", "__import__('os')", "2**4", "1e10", "1//2", "капля", "True", "[2]", "9"*251])
def test_mass_rejects_invalid(expression):
    with pytest.raises(DomainError):
        mass(expression)


def test_price_am1():
    p = price_values(dict(period="2026-08",package_price=28452.5,volume_liters=3.5,grams_per_liter=1555))
    assert p["net_grams"] == 5442.5
    assert p["price_per_gram"] == pytest.approx(5.227836472209463)
    assert f'{p["price_per_gram"]:.3f}' == "5.228"


@pytest.mark.parametrize("field,value", [("package_price",None),("package_price",-1),("package_price",float('nan')),("volume_liters",0),("grams_per_liter",float('inf'))])
def test_invalid_price(field,value):
    data=dict(period="2026-08",package_price=1,volume_liters=1,grams_per_liter=1000)
    data[field]=value
    with pytest.raises(DomainError):price_values(data)


def test_month_range():
    assert months_between("2025-12","2026-02") == ["2025-12","2026-01","2026-02"]
    for value in ("2026-13","2026-1","0000-01"):
        with pytest.raises(DomainError):month(value)
