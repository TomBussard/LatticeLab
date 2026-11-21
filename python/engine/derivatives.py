import copy
import math
from itertools import product
from typing import Callable

from .inputs import Request


ORDERS = {
    "delta": {"spot": 1},
    "gamma": {"spot": 2},
    "vega": {"volatility": 1},
    "theta": {"days": 1},
    "rho": {"rate": 1},
    "vanna": {"spot": 1, "volatility": 1},
    "volga": {"volatility": 2},
    "charm": {"spot": 1, "days": 1},
    "speed": {"spot": 3},
}
UNITS = {
    "delta": "shares",
    "gamma": "EUR / EUR²",
    "vega": "EUR / volatility point",
    "theta": "EUR / day",
    "rho": "EUR / rate point",
    "vanna": "shares / volatility point",
    "volga": "EUR / squared volatility point",
    "charm": "shares / day",
    "speed": "EUR / EUR³",
}


def stencil(axis: str, order: int) -> list[tuple[int, float]]:
    """The offsets and coefficients of the requested finite difference are returned"""
    if axis == "days":
        return [(0, -1.5), (1, 2.0), (2, -0.5)]
    if order == 1:
        return [(-1, -0.5), (1, 0.5)]
    if order == 2:
        return [(-1, 1.0), (0, -2.0), (1, 1.0)]
    return [(-2, -0.5), (-1, 1.0), (1, -1.0), (2, 0.5)]


def shifted_request(request: Request, shifts: dict[str, float]) -> Request:
    """The scenario is copied with the changes in market and time required"""
    result = copy.deepcopy(request)
    for axis, amount in shifts.items():
        if axis == "days":
            result["elapsed_days"] = result.get("elapsed_days", 0.0) + amount
        else:
            result["market"][axis] += amount
    return result


def scale(name: str, basis: int) -> float:
    """Crude derivatives are converted into displayed units"""
    if name in ("vega", "rho", "vanna"):
        return 0.01
    if name == "volga":
        return 0.0001
    if name in ("theta", "charm"):
        return 1.0 / basis
    return 1.0


class Derivatives:
    def __init__(
        self,
        request: Request,
        price_function: Callable[[Request], Request],
        base_price: float | None = None,
    ) -> None:
        """The calculation of the Greeks is prepared with a price cache per scenario"""
        self.request = request
        self.price_function = price_function
        self.cache = {} if base_price is None else {(): base_price}

    def price(self, shifts: dict[str, float]) -> float:
        """The price of the scenario is returned by reusing an already calculated result"""
        key = tuple(sorted((axis, amount) for axis, amount in shifts.items() if amount))
        if key not in self.cache:
            self.cache[key] = self.price_function(shifted_request(self.request, shifts))["price"]
        return self.cache[key]

    def greek(self, name: str) -> float:
        """Combining scenarios to calculate the required derivative"""
        orders = ORDERS[name]
        axes = list(orders)
        stencils = [stencil(axis, orders[axis]) for axis in axes]
        result = 0.0
        for terms in product(*stencils):
            shifts, weight = {}, 1.0
            for axis, (position, coefficient) in zip(axes, terms):
                bump = self.request["bumps"][axis]
                shifts[axis] = position * bump
                weight *= coefficient / bump ** orders[axis]
            result += weight * self.price(shifts)
        # We first express the passage of time in years and then in days in the display
        if "days" in orders:
            result *= self.request["day_basis"]
        if not math.isfinite(result):
            raise ValueError("La dérivée dépasse la précision numérique disponible")
        return result


def greek_row(name: str, raw: float, basis: int) -> Request:
    """The raw derivative and its conversion into the unity of the Greek"""
    return {"raw": raw, "value": raw * scale(name, basis), "unit": UNITS[name], "warning": None}


def unavailable_row(name: str, message: str) -> Request:
    """A Greek not available is reported instead of returning a deceptive value"""
    row = greek_row(name, 0.0, 365)
    row.update(raw=None, value=None, warning=message)
    return row


def relative_error(value: float, reference: float) -> float:
    """A symmetrical relative deviation is calculated by protecting values close to zero."""
    return abs(value - reference) / max(abs(reference), abs(value), 1e-8)


def greek_report(
    request: Request, price_function: Callable[[Request], Request], base_price: float | None = None
) -> Request:
    """The requested Greeks are calculated and those not available are reported."""
    derivative = Derivatives(request, price_function, base_price)
    rows = {}
    for name in request["greeks"]:
        try:
            rows[name] = greek_row(name, derivative.greek(name), request["day_basis"])
        except (ValueError, ZeroDivisionError, OverflowError) as error:
            rows[name] = unavailable_row(name, str(error))
    return rows
