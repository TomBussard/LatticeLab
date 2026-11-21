from time import perf_counter

from .analytic import black_scholes_reference
from .derivatives import greek_report, relative_error
from .inputs import Request, normalize_request
from .pricing import price_request


def request_warnings(request: Request) -> list[str]:
    """Market, product and finite differences warnings are prepared"""
    warnings = []
    if request["market"]["dividend_date"] and request["market"]["dividend"] == 0:
        warnings.append(
            "Aucun dividende futur n'est appliqué ; le spot est supposé observé après les détachements passés"
        )
    if request["grid"]["pruning"] and request["grid"]["mode"] == "binomial":
        warnings.append("Le pruning du modèle s'applique uniquement au trinomial")
    if any(leg["kind"].startswith("digital") for leg in request["legs"]):
        warnings.append(
            "Le payoff discontinu des digitales peut entraîner des oscillations de prix et de grecs"
        )
    if any(leg["_maturity"] == 0 for leg in request["legs"]):
        warnings.append(
            "À l'échéance, les différences finies du payoff ne définissent pas un grec au point de discontinuité"
        )
    for leg in request["legs"]:
        if leg["kind"] == "one_touch_up":
            warnings.append(one_touch_warning(leg))
    dividend_time = request["market"]["_dividend_time"]
    if dividend_time and 2 * request["bumps"]["days"] / request["day_basis"] >= dividend_time:
        warnings.append(
            "La bosse de temps franchit le dividende : thêta et charm incluent ce changement de calendrier"
        )
    return list(dict.fromkeys(warnings))


def one_touch_warning(leg: Request) -> str:
    """How the barrier is observed and when payment is discounted"""
    if leg.get("_touch_settled", False):
        return "One-touch touché à la valorisation : paiement immédiat acquis, état conservé sous les bosses, grecs nuls"
    if leg["monitoring"] == "grid":
        return "One-touch observé aux dates de l'arbre, paiement au premier nœud touché"
    return (
        "One-touch : observation continue approchée par pont brownien, paiement au milieu du pas de franchissement ; "
        "le passage d'un dividende est approché et doit faire l'objet d'un contrôle de convergence"
    )


def conventions(request: Request) -> Request:
    """The units and conventions used in the results are described"""
    return {
        "currency": "EUR",
        "day_count": f"ACT/{request['day_basis']}",
        "rates": "Taux annuels continus",
        "volatility": "Volatilité annuelle en décimal",
        "dividend": "Un dividende fixe daté, distinct du rendement continu",
        "greeks": "Dérivées de la position totale avec les quantités signées et les multiplicateurs",
        "digital_boundary": "Digitale call : S >= K ; digitale put : S < K ; one-touch : S >= H",
        "touch_settlement": "Un one-touch touché à la valorisation est un paiement immédiat acquis, sans risque résiduel",
        "vega_rho_vanna": "Par point de pourcentage",
        "volga": "Par carré de point de volatilité",
        "theta_charm": "Par jour écoulé, spot inchangé et dates d'échéance et de dividende fixes",
    }


def attach_reference(report: Request, request: Request) -> None:
    """An analytical reference is added when its assumptions correspond to all contracts"""
    try:
        reference = black_scholes_reference(request)
    except ValueError as error:
        report.update(reference=None, reference_note=str(error))
        return
    report["reference"] = reference
    report["reference_note"] = "Black-Scholes exact sous les hypothèses de ce marché"
    for name, row in report["greeks"].items():
        row["analytic_value"] = reference["greeks"][name]["value"]
        if row["value"] is not None:
            row["analytic_relative_error"] = relative_error(row["value"], row["analytic_value"])
            if row["analytic_relative_error"] > 0.1:
                row["warning"] = (
                    "Écart supérieur à 10 % avec la référence analytique : augmenter le nombre de pas"
                )


def calculate(raw: Request) -> Request:
    """Collect prices and sensitivities without changing the chosen engine"""
    started = perf_counter()
    request = normalize_request(raw)
    report = price_request(request)
    greek_started = perf_counter()
    report["greeks"] = greek_report(request, price_request, report["price"])
    report["timings"]["greeks"] = perf_counter() - greek_started
    report["timings"]["total"] = perf_counter() - started
    delta = report["greeks"].get("delta", {}).get("value")
    report["hedge_shares"] = -delta if delta is not None else None
    report["warnings"] = request_warnings(request)
    report["schedule"] = [
        {"expiry": leg.get("expiry"), "days": leg["_days"], "maturity": leg["_maturity"]}
        for leg in request["legs"]
    ]
    report["conventions"] = conventions(request)
    attach_reference(report, request)
    return report
