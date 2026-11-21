import math
from statistics import NormalDist

from .derivatives import greek_row
from .inputs import GREEKS, Request, normalize_request


def simple_analytic(request: Request, leg: Request) -> Request | None:
    """On calcule directement le prix et les grecs analytiques pour un strike nul"""
    market = request["market"]
    result = {key: 0.0 for key in GREEKS}
    maturity = leg["_maturity"]
    if leg["strike"] == 0:
        delta = math.exp(-market["yield_rate"] * maturity) if leg["kind"] == "call" else 0.0
        value = delta * market["spot"]
        result.update(price=value, delta=delta, theta=market["yield_rate"] * value, charm=market["yield_rate"] * delta)
    else:
        return None
    return result


def validate_analytic(request: Request, leg: Request) -> None:
    """On vérifie que Black-Scholes peut servir de référence à ce contrat"""
    market = request["market"]
    if leg["american"] or leg["kind"] not in ("call", "put"):
        raise ValueError("Black-Scholes est une référence pour les calls et puts européens uniquement")
    if market["dividend"] and market["_dividend_time"] <= leg["_maturity"]:
        raise ValueError("Black-Scholes n'est pas une référence exacte avec un dividende discret avant l'échéance")
    if leg["_maturity"] == 0:
        raise ValueError("La référence des grecs n'est pas définie à l'échéance")


def bs_terms(request: Request, leg: Request) -> tuple[float, ...]:
    """On prépare les facteurs communs aux formules de Black-Scholes"""
    market = request["market"]
    spot, sigma, rate, yield_rate = (market[key] for key in ("spot", "volatility", "rate", "yield_rate"))
    maturity, strike = leg["_maturity"], leg["strike"]
    width = sigma * math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate - yield_rate + 0.5 * sigma * sigma) * maturity) / width
    d2 = d1 - width
    discount_q = math.exp(-yield_rate * maturity)
    strike_pv = strike * math.exp(-rate * maturity)
    density = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    return spot, sigma, rate, yield_rate, maturity, width, d1, d2, discount_q, strike_pv, density


def analytic_leg(request: Request, leg: Request) -> Request:
    """On calcule le prix et les neuf grecs analytiques d’une option européenne"""
    validate_analytic(request, leg)
    simple = simple_analytic(request, leg)
    if simple is not None:
        return simple
    spot, sigma, rate, q, maturity, width, d1, d2, dq, kp, density = bs_terms(request, leg)
    sign = 1 if leg["kind"] == "call" else -1
    n1, n2 = NormalDist().cdf(sign * d1), NormalDist().cdf(sign * d2)
    delta = sign * dq * n1
    gamma = dq * density / (spot * width)
    vega = spot * dq * density * math.sqrt(maturity)
    theta = -spot * dq * density * sigma / (2 * math.sqrt(maturity)) - sign * rate * kp * n2 + q * spot * delta
    charm = q * delta - dq * density * (2 * (rate - q) * maturity - d2 * width) / (2 * maturity * width)
    return {"price": sign * (spot * dq * n1 - kp * n2), "delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "rho": sign * maturity * kp * n2, "vanna": -dq * density * d2 / sigma,
            "volga": vega * d1 * d2 / sigma, "charm": charm, "speed": -gamma / spot * (1 + d1 / width)}


def black_scholes_reference(raw: Request) -> Request:
    """On additionne les références analytiques avec les quantités signées de la position"""
    request = normalize_request(raw)
    rows = [analytic_leg(request, leg) for leg in request["legs"]]
    weights = [leg["quantity"] * leg["multiplier"] for leg in request["legs"]]
    totals = {key: sum(row[key] * weight for row, weight in zip(rows, weights)) for key in ("price", *GREEKS)}
    greeks = {key: greek_row(key, totals[key], request["day_basis"]) for key in request["greeks"]}
    return {"price": totals["price"], "unit_prices": [row["price"] for row in rows], "greeks": greeks,
            "method": "Black-Scholes analytique", "exact": True}
