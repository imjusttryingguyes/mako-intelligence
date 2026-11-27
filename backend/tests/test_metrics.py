from decimal import Decimal

import pytest

from mako_intelligence.metrics.calculations import cpa, cpc, cr, ctr, ratio


def test_exact_decimal_math() -> None:
    assert cpc(Decimal("120.00"), 8) == Decimal("15.00")
    assert cpa(Decimal("120.00"), 3) == Decimal("40.00")
    assert ctr(5, 100) == Decimal("5")
    assert cr(3, 20) == Decimal("15")
    assert ratio(1, 3) == Decimal(1) / Decimal(3)


@pytest.mark.parametrize("metric,args", [
    (cpa, (100, 0)),
    (cpc, (100, 0)),
    (cr, (0, 0)),
    (ctr, (0, 0)),
])
def test_zero_denominator_is_undefined(metric, args) -> None:
    assert metric(*args) is None


def test_negative_data_rejected() -> None:
    with pytest.raises(ValueError):
        cpa(-1, 1)
    with pytest.raises(ValueError):
        cpa(10, -1)
