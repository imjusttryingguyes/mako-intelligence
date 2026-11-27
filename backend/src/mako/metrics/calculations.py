"""A tiny deterministic metrics kernel; all divisions guard zero denominators."""

from decimal import Decimal


def _nonnegative(value: Decimal | int) -> Decimal:
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Metric inputs must be non-negative finite numbers")
    return result


def ratio(numerator: Decimal | int, denominator: Decimal | int) -> Decimal | None:
    n = _nonnegative(numerator)
    d = _nonnegative(denominator)
    return n / d if d > 0 else None


def ctr(clicks: Decimal | int, impressions: Decimal | int) -> Decimal | None:
    result = ratio(clicks, impressions)
    return result * 100 if result is not None else None


def cpc(cost: Decimal | int, clicks: Decimal | int) -> Decimal | None:
    return ratio(cost, clicks)


def cr(conversions: Decimal | int, clicks: Decimal | int) -> Decimal | None:
    result = ratio(conversions, clicks)
    return result * 100 if result is not None else None


def cpa(cost: Decimal | int, conversions: Decimal | int) -> Decimal | None:
    return ratio(cost, conversions)
