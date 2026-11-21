import ast
import math
from typing import Any, Callable

from .core.option_trade import OptionTrade
from .core.tree import Tree


FUNCTIONS = {"max": max, "min": min, "abs": abs, "sqrt": math.sqrt, "exp": math.exp, "log": math.log}
ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load, ast.Constant,
           ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.IfExp, ast.Compare,
           ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.BoolOp, ast.And, ast.Or)


def custom_payoff(expression: str) -> Callable[[float, float], float]:
    """On valide et on compile une expression mathématique de payoff en S et K"""
    if not isinstance(expression, str) or len(expression) > 500:
        raise ValueError("Le payoff doit être une expression de moins de 500 caractères")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError("Expression de payoff invalide") from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 120:
        raise ValueError("Expression de payoff trop longue")
    for node in nodes:
        validate_expression_node(node)
    code = compile(tree, "<payoff>", "eval")
    # On applique le payoff compilé aux valeurs S et K du scénario
    return lambda spot, strike: float(eval(code, {"__builtins__": {}}, dict(FUNCTIONS, S=spot, K=strike)))


def validate_expression_node(node: ast.AST) -> None:
    """On vérifie que le nœud du payoff utilise uniquement la syntaxe autorisée"""
    if not isinstance(node, ALLOWED):
        raise ValueError("Le payoff accepte uniquement des calculs, comparaisons et fonctions autorisées")
    if isinstance(node, ast.Name) and node.id not in (*FUNCTIONS, "S", "K"):
        raise ValueError(f"Variable inconnue dans le payoff : {node.id}")
    if isinstance(node, ast.Constant):
        if type(node.value) not in (float, int) or not math.isfinite(node.value) or abs(node.value) > 1e12:
            raise ValueError("Constante de payoff invalide")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
            raise ValueError("Fonction de payoff non autorisée")
    if isinstance(node, ast.BoolOp) and any(not isinstance(value, (ast.Compare, ast.BoolOp)) for value in node.values):
        raise ValueError("Les opérateurs and et or doivent relier des comparaisons")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        exponent = node.right
        if not isinstance(exponent, ast.Constant) or type(exponent.value) not in (int, float):
            raise ValueError("La puissance doit être une constante entre 0 et 8")
        if not 0 <= exponent.value <= 8:
            raise ValueError("La puissance doit être une constante entre 0 et 8")


class ProductTrade(OptionTrade):
    def __init__(self, leg: dict[str, Any]) -> None:
        """On crée le contrat du produit demandé à partir des paramètres normalisés"""
        super().__init__(leg["strike"], max(leg["_maturity"], 1e-15), leg["kind"] == "call", leg["american"])
        self.kind = leg["kind"]
        self.payout = leg["payout"]
        self.monitoring = leg["monitoring"]
        self.expression = custom_payoff(leg.get("expression", "")) if self.kind == "custom" else None

    def payoff(self, spot_price: float) -> float:
        """On calcule le paiement du produit pour le prix de l’action indiqué"""
        if self.kind in ("call", "put"):
            return super().payoff(spot_price)
        if self.kind in ("digital_call", "one_touch_up"):
            return self.payout if spot_price >= self.strike else 0.0
        if self.kind == "digital_put":
            return self.payout if spot_price < self.strike else 0.0
        result = self.expression(spot_price, self.strike)
        if not math.isfinite(result):
            raise ValueError("Le payoff personnalisé produit une valeur non finie")
        return max(0.0, result) if self.is_american else result


class ProductTree(Tree):
    def _price_node(self, node: Any, option: ProductTrade) -> None:
        """On valorise le nœud en tenant compte du paiement au premier franchissement du one-touch"""
        if option.kind != "one_touch_up":
            super()._price_node(node, option)
        elif node.price >= option.strike:
            node.option_value = option.payout
        elif option.monitoring == "grid":
            super()._price_node(node, option)
        else:
            node.option_value = self.bridge_value(node, option)

    def bridge_value(self, node: Any, option: ProductTrade) -> float:
        """On estime la valeur du one-touch entre deux dates avec un pont brownien"""
        branches = [(p, child) for p, child in ((node.proba_down, node.next_down),
                    (node.proba_mid, node.next_mid), (node.proba_up, node.next_up)) if child is not None and p > 0]
        expected = sum(p * child.price for p, child in branches)
        shift = max(0.0, node.price * self.fwd_proj - expected)
        value = 0.0
        for probability, child in branches:
            # On approxime le prix avant détachement et le paiement au milieu du pas
            end = child.price + shift
            hit = 1.0 if end >= option.strike else math.exp(
                -2 * math.log(option.strike / node.price) * math.log(option.strike / end)
                / (self.mkt.volatility ** 2 * self.time_step_year))
            value += probability * (hit * option.payout * math.sqrt(self.df) + (1 - hit) * self.df * child.option_value)
        return value
