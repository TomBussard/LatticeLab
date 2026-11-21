import copy
import math
from itertools import product
from typing import Callable

from .inputs import Request


ORDERS = {"delta": {"spot": 1}, "gamma": {"spot": 2}, "vega": {"volatility": 1},
          "theta": {"days": 1}, "rho": {"rate": 1}, "vanna": {"spot": 1, "volatility": 1},
          "volga": {"volatility": 2}, "charm": {"spot": 1, "days": 1}, "speed": {"spot": 3}}
UNITS = {"delta": "actions", "gamma": "EUR / EUR²", "vega": "EUR / point de volatilité",
         "theta": "EUR / jour", "rho": "EUR / point de taux", "vanna": "actions / point de volatilité",
         "volga": "EUR / point de volatilité²", "charm": "actions / jour", "speed": "EUR / EUR³"}


def stencil(axis: str, order: int) -> list[tuple[int, float]]:
    """On renvoie les décalages et les coefficients de la différence finie demandée"""
    if axis == "days":
        return [(0, -1.5), (1, 2.0), (2, -0.5)]
    if order == 1:
        return [(-1, -0.5), (1, 0.5)]
    if order == 2:
        return [(-1, 1.0), (0, -2.0), (1, 1.0)]
    return [(-2, -0.5), (-1, 1.0), (1, -1.0), (2, 0.5)]


def shifted_request(request: Request, shifts: dict[str, float]) -> Request:
    """On copie le scénario avec les variations de marché et de temps demandées"""
    result = copy.deepcopy(request)
    for axis, amount in shifts.items():
        if axis == "days":
            result["elapsed_days"] = result.get("elapsed_days", 0.0) + amount
        else:
            result["market"][axis] += amount
    return result


def scale(name: str, basis: int) -> float:
    """On convertit les dérivées brutes en unités affichées"""
    if name in ("vega", "rho", "vanna"):
        return 0.01
    if name == "volga":
        return 0.0001
    if name in ("theta", "charm"):
        return 1.0 / basis
    return 1.0


class Derivatives:
    def __init__(self, request: Request, price_function: Callable[[Request], Request], base_price: float | None = None) -> None:
        """On prépare le calcul des grecs avec un cache de prix par scénario"""
        self.request = request
        self.price_function = price_function
        self.cache = {} if base_price is None else {(): base_price}

    def price(self, shifts: dict[str, float]) -> float:
        """On renvoie le prix du scénario en réutilisant un résultat déjà calculé"""
        key = tuple(sorted((axis, amount) for axis, amount in shifts.items() if amount))
        if key not in self.cache:
            self.cache[key] = self.price_function(shifted_request(self.request, shifts))["price"]
        return self.cache[key]

    def greek(self, name: str) -> float:
        """On combine les scénarios pour calculer la dérivée demandée"""
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
        # On exprime d'abord le passage du temps en années puis en jours dans l'affichage
        if "days" in orders:
            result *= self.request["day_basis"]
        if not math.isfinite(result):
            raise ValueError("La dérivée dépasse la précision numérique disponible")
        return result


def greek_row(name: str, raw: float, basis: int) -> Request:
    """On met en forme la dérivée brute et sa conversion dans l’unité du grec"""
    return {"raw": raw, "value": raw * scale(name, basis), "unit": UNITS[name],
            "warning": None}


def unavailable_row(name: str, message: str) -> Request:
    """On signale un grec indisponible au lieu de renvoyer une valeur trompeuse"""
    row = greek_row(name, 0.0, 365)
    row.update(raw=None, value=None, warning=message)
    return row


def relative_error(value: float, reference: float) -> float:
    """On calcule un écart relatif symétrique en protégeant les valeurs proches de zéro"""
    return abs(value - reference) / max(abs(reference), abs(value), 1e-8)


def greek_report(request: Request, price_function: Callable[[Request], Request], base_price: float | None = None) -> Request:
    """On calcule les grecs demandés et on signale ceux qui sont indisponibles"""
    derivative = Derivatives(request, price_function, base_price)
    rows = {}
    for name in request["greeks"]:
        try:
            rows[name] = greek_row(name, derivative.greek(name), request["day_basis"])
        except (ValueError, ZeroDivisionError, OverflowError) as error:
            rows[name] = unavailable_row(name, str(error))
    return rows
