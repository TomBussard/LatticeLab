import ast
import math
import platform
import threading
import time
from pathlib import Path
from typing import Any

from engine.derivatives import greek_row, unavailable_row
from engine.inputs import normalize_request
from engine.products import custom_payoff
from engine.service import attach_reference, conventions, request_warnings


WORKBOOK = Path(__file__).resolve().parents[1] / "vba" / "Pricer.xlsm"
EXCEL_LOCK = threading.Lock()
OPERATORS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**", ast.Lt: "<",
             ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}


def status() -> dict[str, Any]:
    """On indique si Excel et le pont VBA sont disponibles sur ce poste"""
    result = {"available": False, "platform": platform.system(), "workbook": WORKBOOK.name}
    if platform.system() != "Windows":
        return dict(result, reason="L'automatisation web VBA nécessite Excel pour Windows ; Excel pour Mac reste non validé")
    try:
        import win32com.client
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"):
            pass
    except (ImportError, OSError):
        return dict(result, reason="Installer Excel pour Windows et la dépendance pywin32")
    if not WORKBOOK.is_file():
        return dict(result, reason="Le classeur VBA n'a pas encore été préparé")
    return dict(result, available=True, reason="Excel détecté ; les macros sont vérifiées au lancement du calcul")


def postfix(expression: str) -> str:
    """On traduit seulement les expressions déjà validées par le langage de payoff"""
    custom_payoff(expression)
    tokens: list[str] = []
    emit_tokens(ast.parse(expression, mode="eval").body, tokens)
    return " ".join(tokens)


def _emit_condition(node: ast.IfExp, tokens: list[str]) -> None:
    """On traduit une condition en sauts qui évaluent uniquement la branche choisie"""
    emit_tokens(node.test, tokens)
    false_jump = len(tokens)
    tokens.append("")
    emit_tokens(node.body, tokens)
    end_jump = len(tokens)
    tokens.append("")
    tokens[false_jump] = f"jf={len(tokens)}"
    emit_tokens(node.orelse, tokens)
    tokens[end_jump] = f"jmp={len(tokens)}"


def _boolean_expression(node: ast.BoolOp) -> ast.AST:
    """On transforme une condition and ou or en branchements avec court-circuit"""
    result = node.values[-1]
    for value in reversed(node.values[:-1]):
        if isinstance(node.op, ast.And):
            result = ast.IfExp(test=value, body=result, orelse=value)
        else:
            result = ast.IfExp(test=value, body=value, orelse=result)
    return result


def emit_tokens(node: ast.AST, tokens: list[str]) -> None:
    """On convertit chaque nœud syntaxique en instructions pour la pile VBA"""
    if isinstance(node, ast.Constant):
        tokens.append("#" + repr(float(node.value)))
    elif isinstance(node, ast.Name):
        tokens.append(node.id)
    elif isinstance(node, ast.IfExp):
        _emit_condition(node, tokens)
    elif isinstance(node, ast.BoolOp):
        emit_tokens(_boolean_expression(node), tokens)
    elif isinstance(node, ast.UnaryOp):
        emit_tokens(node.operand, tokens)
        if isinstance(node.op, ast.USub):
            tokens.append("neg")
    elif isinstance(node, ast.BinOp):
        emit_tokens(node.left, tokens)
        emit_tokens(node.right, tokens)
        tokens.append(OPERATORS[type(node.op)])
    elif isinstance(node, ast.Compare):
        _emit_comparison(node, tokens)
    elif isinstance(node, ast.Call):
        _emit_call(node, tokens)


def _emit_comparison(node: ast.Compare, tokens: list[str]) -> None:
    """On développe les comparaisons chaînées en conditions successives"""
    comparisons = []
    for left, operator, right in zip([node.left, *node.comparators], node.ops, node.comparators):
        comparisons.append(ast.Compare(left=left, ops=[operator], comparators=[right]))
    if len(comparisons) > 1:
        emit_tokens(_boolean_expression(ast.BoolOp(op=ast.And(), values=comparisons)), tokens)
    else:
        emit_tokens(node.left, tokens)
        emit_tokens(node.comparators[0], tokens)
        tokens.append(OPERATORS[type(node.ops[0])])


def _emit_call(node: ast.Call, tokens: list[str]) -> None:
    """On traduit les fonctions mathématiques autorisées en instructions pour VBA"""
    name = node.func.id
    if name in ("max", "min"):
        if len(node.args) < 2:
            raise ValueError("min et max nécessitent au moins deux arguments scalaires")
        emit_tokens(node.args[0], tokens)
        for argument in node.args[1:]:
            emit_tokens(argument, tokens)
            tokens.append(name)
    else:
        if len(node.args) != 1:
            raise ValueError(f"{name} nécessite un argument")
        emit_tokens(node.args[0], tokens)
        tokens.append(name)


def parameters(request: dict[str, Any], leg: dict[str, Any]) -> tuple[Any, ...]:
    """On prépare les champs numériques et contractuels transmis au moteur VBA"""
    market, grid, bumps = request["market"], request["grid"], request["bumps"]
    formula = postfix(leg.get("expression", "")) if leg["kind"] == "custom" else ""
    return (market["spot"], market["rate"], market["volatility"], market["yield_rate"], market["dividend"],
            market["_dividend_time"] or 0, leg["_maturity"], grid["steps"], 3 if grid["mode"] == "trinomial" else 2,
            grid["pruning"], leg["kind"], leg["strike"], leg["american"], leg["payout"], leg["monitoring"], formula,
            bool(leg.get("_touch_settled", False)), 0, 0, 0,
            bumps["spot"], bumps["volatility"], bumps["rate"], bumps["days"] / request["day_basis"])


def run_legs(app: Any, book: Any, request: dict[str, Any], names: list[str]) -> list[tuple[Any, ...]]:
    """On appelle le calcul VBA pour les instruments et les grecs demandés"""
    values = "\n".join(parameter_text(request, leg) for leg in request["legs"])
    rows = app.Run(f"'{book.Name}'!Pricer.RunBatch", values, ",".join(names))
    return _read_rows(rows)


def _read_rows(rows: str) -> list[tuple[Any, ...]]:
    """On décode les lignes numériques du VBA et on fait remonter ses erreurs explicites"""
    if rows.startswith("error:"):
        raise ValueError(rows.removeprefix("error:"))
    return [tuple(value if value.startswith("error:") else float(value or 0) for value in row.split("\t"))
            for row in rows.split("\n")]


def parameter_text(request: dict[str, Any], leg: dict[str, Any]) -> str:
    """On transmet les nombres sans dépendre du séparateur décimal d'Excel"""
    return "\t".join(str(int(value)) if isinstance(value, bool) else str(value) for value in parameters(request, leg))


def summed_greek(rows: list[tuple[Any, ...]], weights: list[float], index: int) -> float:
    """On additionne les dérivées VBA pondérées en refusant les erreurs et les valeurs non finies"""
    for row in rows:
        if isinstance(row[index], str):
            raise ValueError(row[index].removeprefix("error:"))
    result = sum(float(row[index]) * weight for row, weight in zip(rows, weights))
    if not math.isfinite(result):
        raise ValueError("Résultat VBA non fini")
    return result


def greek_rows(request: dict[str, Any], rows: list[tuple[Any, ...]], names: list[str]) -> dict[str, Any]:
    """On met en forme les grecs VBA de la position dans leurs unités d’affichage"""
    result = {}
    weights = [leg["quantity"] * leg["multiplier"] for leg in request["legs"]]
    for index, name in enumerate(names, 6):
        try:
            raw = summed_greek(rows, weights, index)
            result[name] = greek_row(name, raw, request["day_basis"])
        except ValueError as error:
            result[name] = unavailable_row(name, str(error))
    return result


def calculate(raw: dict[str, Any]) -> dict[str, Any]:
    """On vérifie les paramètres et on lance un seul appel Excel à la fois"""
    request = normalize_request(raw)
    state = status()
    if not state["available"]:
        raise RuntimeError(state["reason"])
    with EXCEL_LOCK:
        return calculate_excel(request)


def calculate_excel(request: dict[str, Any], operation: str = "price") -> dict[str, Any]:
    """On ouvre une instance Excel dédiée, on appelle le VBA puis on referme cette instance"""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = book = None
    started = time.perf_counter()
    try:
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.AutomationSecurity = 2
        book = app.Workbooks.Open(str(WORKBOOK), UpdateLinks=0, ReadOnly=True)
        if app.Run(f"'{book.Name}'!Pricer.Version") != "atelier-pricer-v3":
            raise RuntimeError("Version du moteur VBA incompatible")
        startup = time.perf_counter() - started
        return _dispatch_excel(app, book, request, started, startup, operation)
    finally:
        if book is not None:
            book.Close(SaveChanges=False)
        if app is not None:
            app.Quit()
        pythoncom.CoUninitialize()


def _dispatch_excel(app: Any, book: Any, request: dict[str, Any], started: float,
                    startup: float, operation: str) -> dict[str, Any]:
    """On exécute l’export de l’arbre ou la valorisation demandée dans Excel"""
    if operation == "tree":
        return _read_tree(app, book, request)
    result = evaluate_excel(app, book, request, started, startup)
    result["warnings"] = list(dict.fromkeys(result["warnings"] + request_warnings(request)))
    result["conventions"] = conventions(request)
    attach_reference(result, request)
    return result


def export_tree(raw: dict[str, Any]) -> dict[str, Any]:
    """On demande à Excel les nœuds d’un arbre limité à un instrument et douze pas"""
    request = normalize_request(raw)
    if request["grid"]["steps"] > 12 or len(request["legs"]) != 1:
        raise ValueError("L'exploration accepte un instrument et au plus 12 pas")
    leg = request["legs"][0]
    if leg["_maturity"] <= 0 and not leg.get("_touch_settled"):
        raise ValueError("Choisir une option dont l'échéance est future pour explorer un arbre")
    state = status()
    if not state["available"]:
        raise RuntimeError(state["reason"])
    with EXCEL_LOCK:
        return calculate_excel(request, "tree")


def _read_tree(app: Any, book: Any, request: dict[str, Any]) -> dict[str, Any]:
    """On convertit l’export VBA en nœuds et branches pour le graphique"""
    values = parameter_text(request, request["legs"][0])
    rows = _read_rows(app.Run(f"'{book.Name}'!Pricer.ExportTreeText", values))
    nodes, edges = [], []
    for row in rows:
        identity = str(int(row[0]))
        nodes.append({"id": identity, "step": int(row[1]), "spot": row[2], "value": row[3],
                      "probability": row[4], "early_exercise": bool(row[5])})
        for target, probability in zip(row[6:9], row[9:12]):
            if target and probability > 0:
                edges.append({"source": identity, "target": str(int(target)), "probability": probability})
    # On classe les nœuds par date et par prix décroissant
    nodes.sort(key=lambda node: (node["step"], -node["spot"]))
    return {"engine": "vba", "nodes": nodes, "edges": edges, "steps": max(node["step"] for node in nodes),
            "price": nodes[0]["value"]}


def evaluate_excel(app: Any, book: Any, request: dict[str, Any], started: float, startup: float) -> dict[str, Any]:
    """On lance le calcul VBA demandé et on mesure le coût de l’appel à Excel"""
    names = list(request["greeks"])
    rows = run_legs(app, book, request, names)
    result = format_result(request, rows, names)
    result["timings"].update(startup=startup, bridge_total=time.perf_counter() - started)
    result["timings"]["bridge"] = max(0, result["timings"]["bridge_total"] - startup - result["timings"]["total"])
    return result


def format_result(request: dict[str, Any], rows: list[tuple[Any, ...]], names: list[str]) -> dict[str, Any]:
    """On agrège les prix et les grecs VBA avec les quantités signées de la position"""
    values = [float(row[0]) for row in rows]
    positions = [value * leg["quantity"] * leg["multiplier"] for value, leg in zip(values, request["legs"])]
    greeks = greek_rows(request, rows, names)
    delta = greeks.get("delta", {}).get("value")
    timings = {"build": sum(row[1] for row in rows), "price": sum(row[2] for row in rows),
               "total": sum(row[5] for row in rows)}
    timings["greeks"] = max(0, timings["total"] - timings["build"] - timings["price"])
    warnings = [entry["warning"] for entry in greeks.values() if entry["warning"]]
    if any(leg["kind"] == "one_touch_up" and leg["monitoring"] == "continuous" for leg in request["legs"]):
        warnings.append("One-touch : pont brownien, paiement au milieu du pas et détachement approchés")
    return {"engine": "vba", "price": sum(positions), "unit_prices": values, "position_values": positions,
            "greeks": greeks, "hedge_shares": -delta if delta is not None else None, "timings": timings,
            "warnings": list(dict.fromkeys(warnings)), "schedule": schedule(request)}


def schedule(request: dict[str, Any]) -> list[dict[str, Any]]:
    """On renvoie les dates et les durées effectivement transmises au moteur"""
    return [{"expiry": leg.get("expiry"), "days": leg["_days"], "maturity": leg["_maturity"]}
            for leg in request["legs"]]
