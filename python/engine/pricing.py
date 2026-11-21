import math
from time import perf_counter

from .core.market import Market
from .core.tree import NbNextNodes
from .inputs import Request, normalize_request
from .products import ProductTrade, ProductTree


def make_tree(request: Request, maturity: float) -> ProductTree:
    """On crée un arbre du type demandé pour le marché et la maturité fournis"""
    market = request["market"]
    grid = request["grid"]
    model = Market(market["spot"], market["rate"], market["volatility"], market["yield_rate"],
                   market["dividend"], market["_dividend_time"])
    mode = NbNextNodes.TRINOMIAL if grid["mode"] == "trinomial" else NbNextNodes.BINOMIAL
    return ProductTree(model, maturity, grid["steps"], mode, grid["pruning"])


def release_tree(tree: ProductTree) -> None:
    """On coupe les liens de l’arbre pour libérer ses nœuds après un calcul"""
    trunk = tree.last_trunk or tree.root
    while trunk is not None:
        previous = trunk.prev_mid
        node = trunk.top()
        while node is not None:
            next_node = node.down_node
            node.next_down = node.next_mid = node.next_up = None
            node.down_node = node.up_node = None
            node = next_node
        trunk.prev_mid = None
        trunk = previous
    tree.root = tree.last_trunk = None


def immediate_price(request: Request, leg: Request, trade: ProductTrade) -> float | None:
    """On traite les paiements connus sans construire un arbre inutile"""
    spot = request["market"]["spot"]
    if leg["kind"] == "one_touch_up" and leg.get("_touch_settled", False):
        return leg["payout"]
    if leg["_maturity"] == 0:
        return trade.payoff(spot)
    if leg["kind"] == "one_touch_up" and spot >= leg["strike"]:
        return leg["payout"]
    return None


def price_leg(request: Request, leg: Request, trees: dict[float, ProductTree], times: Request) -> float:
    """On valorise une ligne en réutilisant l’arbre de son échéance"""
    trade = ProductTrade(leg)
    immediate = immediate_price(request, leg, trade)
    if immediate is not None:
        return immediate
    maturity = leg["_maturity"]
    if maturity not in trees:
        started = perf_counter()
        trees[maturity] = make_tree(request, maturity)
        trees[maturity].build_tree()
        times["build"] += perf_counter() - started
    started = perf_counter()
    value = trees[maturity].price(trade)
    times["price"] += perf_counter() - started
    return value


def price_request(raw: Request) -> Request:
    """On calcule les prix unitaires, la valeur de position et les temps du moteur"""
    started = perf_counter()
    request = normalize_request(raw)
    times = {"build": 0.0, "price": 0.0, "total": 0.0, "greeks": 0.0}
    trees = {}
    try:
        prices = [price_leg(request, leg, trees, times) for leg in request["legs"]]
    finally:
        for tree in trees.values():
            release_tree(tree)
    values = [price * leg["quantity"] * leg["multiplier"] for price, leg in zip(prices, request["legs"])]
    if not all(math.isfinite(value) for value in (*prices, *values, sum(values))):
        raise ValueError("Le prix ou la valeur de position dépasse la précision numérique disponible")
    times["total"] = perf_counter() - started
    return {"engine": "python", "price": sum(values), "unit_prices": prices,
            "position_values": values, "timings": times}


def tree_nodes(tree: ProductTree) -> tuple[list[Request], dict[int, str]]:
    """On relève les valeurs des nœuds pour afficher un petit arbre"""
    columns = []
    trunk = tree.last_trunk
    while trunk is not None:
        columns.append(trunk)
        trunk = trunk.prev_mid
    nodes, identifiers = [], {}
    for step, trunk in enumerate(reversed(columns)):
        node = trunk.top()
        position = 0
        while node is not None:
            identifier = f"{step}-{position}"
            identifiers[id(node)] = identifier
            nodes.append({"id": identifier, "step": step, "spot": node.price,
                          "value": node.option_value, "probability": node.reach_probability, "_node": node})
            position += 1
            node = node.down_node
    return nodes, identifiers


def tree_edges(nodes: list[Request], identifiers: dict[int, str], trade: ProductTrade) -> list[Request]:
    """On relie les nœuds affichés avec leurs probabilités de transition"""
    edges = []
    last_step = max(row["step"] for row in nodes)
    for row in nodes:
        node = row.pop("_node")
        payoff = trade.payoff(node.price)
        row["early_exercise"] = (trade.is_american and row["step"] < last_step and payoff > 0
                                 and abs(node.option_value - payoff) < 1e-10)
        branches = ((node.proba_down, node.next_down), (node.proba_mid, node.next_mid), (node.proba_up, node.next_up))
        for probability, child in branches:
            if child is not None and probability > 0:
                edges.append({"source": row["id"], "target": identifiers[id(child)], "probability": probability})
    return edges


def settled_tree(request: Request, leg: Request) -> Request:
    """On affiche seulement le paiement connu lorsqu'un one-touch est déjà touché à la valorisation"""
    node = {"id": "0-0", "step": 0, "spot": request["market"]["spot"], "value": leg["payout"],
            "probability": 1.0, "early_exercise": False}
    return {"nodes": [node], "edges": [], "steps": 0, "price": leg["payout"], "engine": "python",
            "note": "Paiement immédiat acquis : il n'y a plus de trajectoire future à explorer"}


def export_tree(raw: Request) -> Request:
    """On limite la visualisation aux petits arbres pour garder les nœuds lisibles"""
    request = normalize_request(raw)
    if len(request["legs"]) != 1 or request["grid"]["steps"] > 12:
        raise ValueError("L'exploration affiche un instrument et au maximum 12 pas")
    leg = request["legs"][0]
    if leg["kind"] == "one_touch_up" and leg.get("_touch_settled", False):
        return settled_tree(request, leg)
    trade = ProductTrade(leg)
    if leg["_maturity"] == 0:
        raise ValueError("Choisir une option avec une échéance future pour afficher son arbre")
    tree = make_tree(request, leg["_maturity"])
    try:
        price = tree.price(trade)
        nodes, identifiers = tree_nodes(tree)
        edges = tree_edges(nodes, identifiers, trade)
        return {"nodes": nodes, "edges": edges, "steps": tree.nb_steps, "price": price, "engine": "python"}
    finally:
        release_tree(tree)
