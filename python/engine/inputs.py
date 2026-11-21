import copy
import math
from datetime import date
from typing import Any


GREEKS = ("delta", "gamma", "vega", "theta", "rho", "vanna", "volga", "charm", "speed")
KINDS = ("call", "put", "digital_call", "digital_put", "one_touch_up", "custom")
Request = dict[str, Any]


def number(value: Any, name: str) -> float:
    """We refuse non-digital values before building the market"""
    if isinstance(value, bool):
        raise ValueError(f"{name} doit être un nombre")
    try:
        result = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} doit être un nombre") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} doit être fini")
    return result


def calendar(value: Any, name: str) -> date:
    """Dates are read in ISO format to avoid ambiguities day and month"""
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{name} doit être une date AAAA-MM-JJ valide") from error


def normalize_market(raw: Request, valuation: date, basis: int, elapsed: float) -> Request:
    """The continuous return is distinguished from the fixed dividend dated"""
    result = {key: number(raw.get(key), key) for key in ("spot", "volatility", "rate")}
    for key in ("yield_rate", "dividend"):
        result[key] = number(raw.get(key, 0), key)
    if result["spot"] <= 0 or result["volatility"] <= 0 or result["dividend"] < 0:
        raise ValueError(
            "Il faut un spot et une volatilité positifs, et un dividende positif ou nul"
        )
    result["dividend_date"] = raw.get("dividend_date") or None
    result["_dividend_time"] = None
    if result["dividend"]:
        ex_date = calendar(result["dividend_date"], "La date de dividende")
        result["_dividend_time"] = ((ex_date - valuation).days - elapsed) / basis
        if result["_dividend_time"] <= 0:
            result["dividend"] = 0.0
            result["_dividend_time"] = None
    return result


def normalize_grid(raw: Request) -> Request:
    """Check the number of steps and the threshold of pruning"""
    steps = number(raw.get("steps", 200), "Le nombre de pas")
    if steps < 1 or steps != int(steps):
        raise ValueError("Le nombre de pas doit être un entier positif")
    mode = str(raw.get("mode", "trinomial")).lower()
    if mode not in ("binomial", "trinomial"):
        raise ValueError("Choisir un arbre binomial ou trinomial")
    pruning = number(raw.get("pruning", 1e-10), "Le pruning")
    if not 0 <= pruning < 1:
        raise ValueError("Le pruning doit être compris entre 0 inclus et 1 exclu")
    return {"steps": int(steps), "mode": mode, "pruning": pruning}


def normalize_leg(raw: Request, valuation: date, basis: int, elapsed: float) -> Request:
    """The signed quantities and expiries for each line shall be retained."""
    result = copy.deepcopy(raw)
    if result.get("kind") not in KINDS:
        raise ValueError("Type de produit inconnu")
    if "strike" not in raw:
        raise ValueError("Le strike ou la barrière est indispensable")
    for key, default in (("strike", 0), ("quantity", 1), ("multiplier", 1), ("payout", 1)):
        result[key] = number(raw.get(key, default), key)
    if result["strike"] < 0 or result["multiplier"] <= 0 or result["payout"] < 0:
        raise ValueError(
            "Strike et montant doivent être positifs ou nuls, multiplicateur strictement positif"
        )
    result["american"] = raw.get("american", False)
    if not isinstance(result["american"], bool):
        raise ValueError("Le mode américain doit être un booléen")
    expiry = calendar(raw.get("expiry"), "L'échéance")
    result["_days"] = (expiry - valuation).days - elapsed
    settled = result.get("_touch_settled", False) and result["kind"] == "one_touch_up"
    if expiry < valuation or (result["_days"] < -1e-10 and not settled):
        raise ValueError("Une échéance précède la date de valorisation ou la bosse de temps")
    result["_maturity"] = max(0, result["_days"] / basis)
    validate_product(result)
    return result


def normalize_legs(
    raw: list[Request], valuation: date, basis: int, elapsed: float, spot: float
) -> list[Request]:
    """The instruments are prepared by keeping the one-touch payments already acquired"""
    result = []
    for source in raw:
        leg = copy.deepcopy(source)
        if leg.get("kind") == "one_touch_up":
            settled = leg.get("_touch_settled", False)
            if not isinstance(settled, bool):
                raise ValueError("L'état de règlement du one-touch doit être un booléen")
            leg["_touch_settled"] = settled or spot >= number(leg.get("strike"), "La barrière")
        result.append(normalize_leg(leg, valuation, basis, elapsed))
    return result


def validate_product(leg: Request) -> None:
    """The choice of exercise and barrier observation of the product is checked"""
    if leg["kind"] in ("digital_call", "digital_put", "one_touch_up") and leg["american"]:
        raise ValueError(
            "Le mode américain concerne les options vanilles et les payoffs personnalisés"
        )
    leg["monitoring"] = leg.get("monitoring", "continuous")
    if leg["monitoring"] not in ("continuous", "grid"):
        raise ValueError("Observation de barrière inconnue")
    if leg["kind"] == "one_touch_up" and leg["strike"] <= 0:
        raise ValueError("La barrière doit être strictement positive")


def normalize_bumps(raw: Request, spot: float) -> Request:
    """Variations used for finite differences are prepared and verified"""
    defaults = {"spot": spot * 0.02, "volatility": 0.005, "rate": 0.001, "days": 1.0}
    result = {key: number(raw.get(key, value), key) for key, value in defaults.items()}
    if any(value <= 0 for value in result.values()):
        raise ValueError("Les bosses doivent être strictement positives")
    return result


def normalize_request(raw: Request) -> Request:
    """A copy of the calculation parameters is checked and normalized."""
    result = copy.deepcopy(raw)
    valuation = calendar(raw.get("valuation_date"), "La date de valorisation")
    basis = number(raw.get("day_basis", 365), "La base annuelle")
    if basis not in (360, 365):
        raise ValueError("Choisir ACT/360 ou ACT/365")
    elapsed = number(raw.get("elapsed_days", 0), "Le temps écoulé")
    if elapsed < 0:
        raise ValueError("Le temps écoulé doit être positif ou nul")
    result.update(day_basis=int(basis), elapsed_days=elapsed, valuation_date=valuation.isoformat())
    result["market"] = normalize_market(raw.get("market", {}), valuation, int(basis), elapsed)
    result["grid"] = normalize_grid(raw.get("grid", {}))
    result["legs"] = normalize_legs(
        raw.get("legs", []), valuation, int(basis), elapsed, result["market"]["spot"]
    )
    if not result["legs"]:
        raise ValueError("Ajouter au moins un instrument")
    result["bumps"] = normalize_bumps(raw.get("bumps", {}), result["market"]["spot"])
    result["greeks"] = list(dict.fromkeys(raw.get("greeks", ["delta"])))
    if any(name not in GREEKS for name in result["greeks"]):
        raise ValueError("Grec inconnu")
    return result
