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
            "No future cash dividend is applied. The spot accounts for past ex-dividend dates."
        )
    if request["grid"]["pruning"] and request["grid"]["mode"] == "binomial":
        warnings.append("Pruning applies only to the trinomial tree")
    if any(leg["kind"].startswith("digital") for leg in request["legs"]):
        warnings.append(
            "Digital payoffs can cause prices and Greeks to oscillate as the grid changes."
        )
    if any(leg["_maturity"] == 0 for leg in request["legs"]):
        warnings.append(
            "At expiry the payoff has no derivative at a discontinuity."
        )
    for leg in request["legs"]:
        if leg["kind"] == "one_touch_up":
            warnings.append(one_touch_warning(leg))
    dividend_time = request["market"]["_dividend_time"]
    if dividend_time and 2 * request["bumps"]["days"] / request["day_basis"] >= dividend_time:
        warnings.append(
            "The time bump crosses the dividend date, which affects theta and charm."
        )
    return list(dict.fromkeys(warnings))


def one_touch_warning(leg: Request) -> str:
    """How the barrier is observed and when payment is discounted"""
    if leg.get("_touch_settled", False):
        return "A barrier touched at valuation pays immediately. Bumped scenarios preserve that state and the Greeks are zero."
    if leg["monitoring"] == "grid":
        return "The barrier is checked on tree dates and pays at the first node that reaches it."
    return (
        "A Brownian bridge approximates continuous barrier monitoring, with payment halfway through the crossing step. "
        "Check grid convergence when a step includes a cash dividend."
    )


def conventions(request: Request) -> Request:
    """The units and conventions used in the results are described"""
    return {
        "currency": "EUR",
        "day_count": f"ACT/{request['day_basis']}",
        "rates": "Continuously compounded annual rates",
        "volatility": "Annualised volatility as a decimal",
        "dividend": "One dated cash dividend and a separate continuous dividend yield",
        "greeks": "Sensitivities of the entire position including signed quantities and multipliers",
        "digital_boundary": "Digital call at S >= K, digital put at S < K, up one-touch at S >= H",
        "touch_settlement": "A barrier already touched at valuation pays immediately and has no remaining exposure",
        "vega_rho_vanna": "Per percentage point",
        "volga": "Per squared volatility point",
        "theta_charm": "Per elapsed day with spot, expiry and ex-dividend dates held fixed",
    }


def attach_reference(report: Request, request: Request) -> None:
    """An analytical reference is added when its assumptions correspond to all contracts"""
    try:
        reference = black_scholes_reference(request)
    except ValueError as error:
        report.update(reference=None, reference_note=str(error))
        return
    report["reference"] = reference
    report["reference_note"] = "Black-Scholes value under these market assumptions"
    for name, row in report["greeks"].items():
        row["analytic_value"] = reference["greeks"][name]["value"]
        if row["value"] is not None:
            row["analytic_relative_error"] = relative_error(row["value"], row["analytic_value"])
            if row["analytic_relative_error"] > 0.1:
                row["warning"] = (
                    "The estimate differs from the analytical value by more than 10%. Try a finer grid."
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
