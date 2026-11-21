import copy
import math
import statistics
import time
from collections.abc import Callable

from engine.inputs import GREEKS, normalize_request, number


ENGINES = ("python", "vba")


def calculator(engine: str) -> Callable:
    """Returns the calculation function of the requested Python or VBA engine"""
    if engine == "python":
        from engine.service import calculate
    elif engine == "vba":
        from excel_bridge import calculate
    else:
        raise ValueError("Moteur inconnu")
    return calculate


def selected_engines(request: dict) -> tuple:
    """The same order is kept for tables and comparison curves"""
    engine = request.get("engine", "python")
    if engine not in ("python", "vba", "both"):
        raise ValueError("Choisir Python, VBA ou les deux moteurs")
    return ENGINES if engine == "both" else (engine,)


def run_engines(request: dict, progress: Callable) -> dict:
    """The results are calculated with each selected engine"""
    results = {}
    for engine in selected_engines(request):
        progress("Calcul " + engine.upper())
        results[engine] = calculator(engine)(request)
    return results


def metric_value(report: dict, metric: str) -> float:
    """Read a price or a Greek in the units reported by the engine."""
    if metric == "price":
        return report["price"]
    row = report["greeks"].get(metric, {})
    value = row.get("value")
    if value is None or not math.isfinite(value):
        raise ValueError(row.get("warning") or f"Le grec {metric} est indisponible")
    return value


def price_only(request: dict, metric: str = "price") -> dict:
    """A copy is prepared which calculates only the price or the Greek studied"""
    result = copy.deepcopy(request)
    result["greeks"] = [] if metric == "price" else [metric]
    return result


def reference_value(request: dict, metric: str, steps: list, progress: Callable) -> dict:
    """Choose Black-Scholes or a finer Python tree as a reference"""
    from engine.analytic import black_scholes_reference

    work = price_only(request, metric)
    try:
        value = metric_value(black_scholes_reference(work), metric)
        return {"value": value, "label": "Black–Scholes analytique", "empirical": False}
    except ValueError:
        maximum = max(steps)
        if maximum >= 10000:
            raise ValueError("Choisir moins de 10 000 pas pour comparer avec un arbre plus précis")
    # If not, we take a Python grid finer than all the points compared
    count = min(10000, maximum * 2)
    work["grid"]["steps"] = count
    progress(f"Référence PYTHON — {count} pas")
    report = calculator("python")(work)
    return {
        "value": metric_value(report, metric),
        "label": f"Arbre PYTHON à {count} pas",
        "empirical": True,
        "steps": count,
    }


def convergence(request: dict, settings: dict, progress: Callable) -> dict:
    """Measure grid convergence while holding the contract and pruning threshold fixed."""
    tolerance = number(settings.get("tolerance", 0.001), "La tolérance")
    if tolerance <= 0:
        raise ValueError("La tolérance doit être strictement positive")
    steps = automatic_steps(request)
    metric = settings.get("metric", "price")
    reference = reference_value(request, metric, steps, progress)
    rows = _convergence_rows(request, metric, steps, reference, progress)
    return {
        "rows": rows,
        "reference": reference,
        "tolerance": tolerance,
        "thresholds": tolerance_results(rows, tolerance),
        "note": "La précision concerne les nombres de pas testés ; la convergence peut osciller",
    }


def _convergence_rows(
    request: dict, metric: str, steps: list, reference: dict, progress: Callable
) -> list:
    """Measure the result and its error for each number of steps"""
    rows = []
    for engine in selected_engines(request):
        work = price_only(request, metric)
        for count in steps:
            progress(f"{engine.upper()} — {count} pas")
            work["grid"]["steps"] = count
            report = _grid_calculation(engine, work)
            value = metric_value(report, metric)
            error = abs(value - reference["value"])
            rows.append(
                {
                    "engine": engine,
                    "steps": count,
                    "value": value,
                    "error": error,
                    "relative_error": error / abs(reference["value"])
                    if reference["value"]
                    else None,
                    "seconds": report["timings"]["total"],
                }
            )
    return rows


def _grid_calculation(engine: str, request: dict) -> dict:
    """The parameters are valued by specifying the number of steps if an error occurs"""
    try:
        return calculator(engine)(request)
    except (ValueError, RuntimeError) as error:
        grid = request["grid"]
        raise ValueError(
            f"{engine.upper()}, {grid['steps']} pas, pruning {grid['pruning']:g} : {error}"
        ) from error


def tolerance_results(rows: list, tolerance: float) -> list:
    """The number of steps from which all points tested meet the tolerance shall be recorded."""
    result = []
    for engine in sorted(set(row["engine"] for row in rows)):
        # The points are sorted by number of steps
        group = sorted(
            (row for row in rows if row["engine"] == engine), key=lambda row: row["steps"]
        )
        sustained = [
            row["steps"]
            for index, row in enumerate(group)
            if all(item["error"] < tolerance for item in group[index:])
        ]
        result.append({"engine": engine, "remaining_tested": min(sustained, default=None)})
    return result


def benchmark(request: dict, progress: Callable) -> dict:
    """Engine times are compared with two repetitions by number of steps"""
    rows = []
    for engine in selected_engines(request):
        work = price_only(request)
        for count in automatic_steps(request):
            work["grid"]["steps"] = count
            progress(f"{engine.upper()} — {count} pas — 2 répétitions")
            rows.append(_benchmark_point(engine, work))
    return {
        "rows": rows,
        "repeats": 2,
        "note": "Chaque instrument est construit et valorisé séparément dans les deux moteurs, sans cache ; "
        "médianes des sommes par position, calcul seul = construction + remontée ; "
        "démarrage Excel et aller-retour mesurés séparément",
    }


def _benchmark_point(engine: str, request: dict) -> dict:
    """The engine time is separated from the return time from the call"""
    samples = [_benchmark_sample(engine, request) for _ in range(2)]
    keys = set.intersection(*(set(sample) for sample in samples)) - {"value"}
    row = {key: statistics.median(sample[key] for sample in samples) for key in keys}
    row.update(engine=engine, steps=request["grid"]["steps"], value=samples[-1]["value"])
    return row


def _benchmark_sample(engine: str, request: dict) -> dict:
    """A complete calculation is measured by building each instrument separately"""
    start = time.perf_counter()
    reports = []
    for leg in request["legs"]:
        work = copy.deepcopy(request)
        work["legs"] = [copy.deepcopy(leg)]
        reports.append(calculator(engine)(work))
    keys = set.intersection(*(set(report["timings"]) for report in reports))
    sample = {key: sum(report["timings"][key] for report in reports) for key in keys}
    sample.update(
        core=sample["build"] + sample["price"],
        roundtrip=time.perf_counter() - start,
        value=sum(report["price"] for report in reports),
    )
    return sample


def tree_view(request: dict, progress: Callable) -> dict:
    """The detail is limited to a small tree legible in the browser"""
    results = {}
    if request["grid"]["steps"] > 12:
        raise ValueError("La visualisation détaillée est limitée à 12 pas")
    request = copy.deepcopy(request)
    request["legs"] = request["legs"][:1]
    for engine in selected_engines(request):
        progress("Construction des nœuds " + engine.upper())
        if engine == "python":
            from engine.pricing import export_tree
        else:
            from excel_bridge import export_tree
        results[engine] = export_tree(request)
    return results


def automatic_steps(request: dict) -> list:
    """The points of the graphs are selected from the number of steps requested"""
    maximum = number(request["grid"]["steps"], "Le nombre de pas")
    if not 1 <= maximum <= 10000 or maximum != int(maximum):
        raise ValueError("Choisir un nombre entier de pas entre 1 et 10 000")
    return sorted(
        set(max(1, round(maximum * ratio)) for ratio in (0.0625, 0.125, 0.25, 0.5, 0.75, 1))
    )


def greek_curve(request: dict, settings: dict, progress: Callable) -> dict:
    """The curve is calculated only for the Greek opened by the user"""
    from engine.derivatives import UNITS

    metric = settings.get("metric")
    if metric not in GREEKS:
        raise ValueError("Choisir un grec disponible")
    request = normalize_request(request)
    center = request["market"]["spot"]
    spots = [center * (0.8 + index * 0.05) for index in range(9)]
    rows = []
    for engine in selected_engines(request):
        work = price_only(request, metric)
        for spot in spots:
            progress(f"{engine.upper()} — spot {spot:g}")
            work["market"]["spot"] = spot
            report = calculator(engine)(work)
            rows.append({"engine": engine, "spot": spot, "value": metric_value(report, metric)})
    return {"rows": rows, "metric": metric, "unit": UNITS[metric]}


def execute(payload: dict, progress: Callable) -> dict:
    """Route a request to its pricing or analysis routine."""
    request = normalize_request(payload["request"])
    settings = payload.get("settings", {})
    action = payload.get("action", "price")
    if action in ("price", "greeks"):
        return {"action": action, "results": run_engines(request, progress)}
    if action == "tree":
        return {"action": action, "results": tree_view(request, progress)}
    if action == "benchmark":
        return {"action": action, **benchmark(request, progress)}
    functions = {"convergence": convergence, "curve": greek_curve}
    if action not in functions:
        raise ValueError("Analyse inconnue")
    return {"action": action, **functions[action](request, settings, progress)}
