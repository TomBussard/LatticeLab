"""Arbre binomial/trinomial du cours, avec un dividende discret."""

import math
from enum import Enum

from .market import Market
from .node import Node, TrunkNode
from .option_trade import OptionTrade


class NbNextNodes(Enum):

    BINOMIAL = 2
    TRINOMIAL = 3


class Tree:
    def __init__(
        self,
        mkt: Market,
        maturity: float,
        nb_steps: int,
        nb_next_nodes: NbNextNodes = NbNextNodes.BINOMIAL,
        pruning_threshold: float = 1e-10,
    ) -> None:
        """On prépare les facteurs de projection et les paramètres de l’arbre"""
        self._validate_parameters(maturity, nb_steps, nb_next_nodes)
        self.mkt = mkt
        self.maturity = maturity
        self.nb_steps = nb_steps
        self.nb_next_nodes = nb_next_nodes
        # On peut mettre 0 pour désactiver l'élagage du trinomial et garder tout l'arbre
        if not math.isfinite(pruning_threshold) or not 0.0 <= pruning_threshold < 1.0:
            raise ValueError("Le seuil d'élagage doit être compris entre 0 et 1 exclu.")
        self.pruning_threshold = pruning_threshold
        # On découpe la durée totale en N intervalles de même longueur
        self.time_step_year = maturity / nb_steps

        self.df = math.exp(-mkt.int_rate * self.time_step_year)
        self.fwd_proj = math.exp((mkt.int_rate - mkt.div_yield) * self.time_step_year)

        self.variance_factor = math.expm1(mkt.volatility ** 2 * self.time_step_year)
        self.sqrt_alpha, self.alpha = self._calculate_alpha()
        self.probas_no_div = self._calculate_proba_no_div()
        # On vérifie une seule fois les probabilités constantes hors dividende
        Node(mkt.s0).set_probabilities(*self.probas_no_div)
        # On repère le pas du dividende une fois, avant de construire les nœuds
        self.div_step = self._dividend_step()

        self.root: TrunkNode | None = None
        self.last_trunk: TrunkNode | None = None

    @staticmethod
    def _validate_parameters(maturity: float, nb_steps: int, mode: NbNextNodes) -> None:
        """On contrôle la maturité, le nombre de pas et le type d’arbre"""
        if not math.isfinite(maturity) or maturity <= 0:
            raise ValueError("La maturité doit être positive et finie.")
        if type(nb_steps) is not int or nb_steps <= 0:
            raise ValueError("Le nombre de pas doit être un entier positif.")
        if not isinstance(mode, NbNextNodes):
            raise ValueError("Choisir NbNextNodes.BINOMIAL ou TRINOMIAL.")

    def _calculate_alpha(self) -> tuple[float, float]:
        """On calcule le rapport multiplicatif entre deux prix voisins"""
        if self.nb_next_nodes is NbNextNodes.BINOMIAL:

            epsilon = self.variance_factor
            sqrt_alpha = 1.0 + epsilon / 2.0 + math.sqrt(epsilon * (1.0 + epsilon / 4.0))
            alpha = sqrt_alpha ** 2
        else:

            alpha = math.exp(self.mkt.volatility * math.sqrt(3.0 * self.time_step_year))
            sqrt_alpha = math.sqrt(alpha)
        if alpha <= 1.0:
            raise ValueError("Volatilité trop petite pour distinguer les nœuds de la grille.")
        return sqrt_alpha, alpha

    def _calculate_proba_no_div(self) -> tuple[float, float, float]:
        """On calcule les probabilités constantes hors détachement du dividende"""
        if self.nb_next_nodes is NbNextNodes.BINOMIAL:

            up = 1.0 / (1.0 + self.sqrt_alpha)
            return 1.0 - up, 0.0, up
        alpha = self.alpha

        down = self.variance_factor / ((1.0 - alpha) * (alpha ** -2 - 1.0))
        up = down / alpha
        return down, 1.0 - down - up, up

    def _dividend_step(self) -> int | None:
        """On repère le pas qui contient la date de détachement du dividende"""
        date = self.mkt.t_ex_div

        if self.mkt.div_amount == 0 or date is None or date > self.maturity:
            return None
        position = date / self.time_step_year
        nearest = round(position)

        if math.isclose(position, nearest, rel_tol=0.0, abs_tol=1e-10):
            position = float(nearest)

        return max(0, math.ceil(position) - 1)

    def _moments(self, spot: float, step: int) -> tuple[float, float]:
        """On calcule l’espérance et la variance du prix suivant en tenant compte du dividende"""

        expected = spot * self.fwd_proj
        adjusted_spot = spot
        if step == self.div_step:

            after_div = (step + 1) * self.time_step_year - self.mkt.t_ex_div
            after_div = max(0.0, after_div)
            drift = self.mkt.int_rate - self.mkt.div_yield
            # On retire le dividende projeté jusqu'à la fin du pas
            expected -= self.mkt.div_amount * math.exp(drift * after_div)

            adjusted_spot -= self.mkt.div_amount * after_div / self.time_step_year

        if expected <= 0:
            raise ValueError(
                f"Le dividende rend le forward négatif ou nul pour S={spot:.6g}. "
                "La grille positive du cours ne couvre pas ce cas."
            )
        # On renvoie bien une variance, donc le carré d'un écart-type
        variance = adjusted_spot ** 2 * self.fwd_proj ** 2 * self.variance_factor
        return expected, variance

    def _calculate_proba_with_div(
        self, expected: float, variance: float, middle: float,
        alpha: float | None = None,
    ) -> tuple[float, float, float]:
        """On ajuste les probabilités aux deux premiers moments du prix après dividende"""
        alpha = self.alpha if alpha is None else alpha

        relative_gap = (expected - middle) / middle

        second_gap = variance / middle ** 2 + relative_gap * (expected / middle + 1.0)
        # On résout les trois équations : somme des poids, moyenne et second moment
        down = (second_gap - (alpha + 1.0) * relative_gap) / (
            (1.0 - alpha) * (alpha ** -2 - 1.0)
        )
        up = (relative_gap - (1.0 / alpha - 1.0) * down) / (alpha - 1.0)

        return down, 1.0 - down - up, up

    def _connect(self, node: Node, candidate: Node, step: int) -> Node:
        """On relie un nœud aux successeurs utiles de la colonne suivante"""
        expected, variance = node.price * self.fwd_proj, 0.0
        if step == self.div_step:
            expected, variance = self._moments(node.price, step)

        if self.nb_next_nodes is NbNextNodes.TRINOMIAL and node.reach_probability < self.pruning_threshold:
            return self._connect_pruned(node, candidate, expected)

        trinomial = self.nb_next_nodes is NbNextNodes.TRINOMIAL or step == self.div_step
        if trinomial:

            middle = candidate.closest(expected, self.alpha)
            node.next_mid = middle
            node.next_up = middle.upper(self.alpha)
            node.next_down = middle.lower(self.alpha)
        else:

            node.next_up = candidate.closest(expected * self.sqrt_alpha, self.alpha)
            node.next_down = node.next_up.lower(self.alpha)
        if step == self.div_step:
            node.set_probabilities(*self._dividend_branches(node, expected, variance))
        else:
            # On réutilise les probabilités déjà vérifiées au lieu de les tester à chaque nœud
            node.proba_down, node.proba_mid, node.proba_up = self.probas_no_div
        return node.next_mid if trinomial else node.next_down

    def _dividend_branches(self, node: Node, expected: float, variance: float) -> tuple[float, float, float]:
        """On élargit les branches du dividende jusqu’à obtenir des probabilités utilisables"""
        probabilities = self._calculate_proba_with_div(expected, variance, node.next_mid.price)
        branch_alpha = self.alpha
        while probabilities[1] < 0.0 and min(probabilities[0], probabilities[2]) >= 0.0:
            node.next_up = node.next_up.upper(self.alpha)
            node.next_down = node.next_down.lower(self.alpha)
            branch_alpha *= self.alpha
            probabilities = self._calculate_proba_with_div(
                expected, variance, node.next_mid.price, branch_alpha,
            )
        return probabilities

    def _connect_pruned(self, node: Node, candidate: Node, expected: float) -> Node:
        """On prolonge un nœud très improbable par une seule branche centrale"""
        node.next_mid = candidate.closest(expected, self.alpha)

        node.proba_down, node.proba_mid, node.proba_up = 0.0, 1.0, 0.0
        return node.next_mid

    @staticmethod
    def _propagate_probability(node: Node) -> None:
        """On cumule les probabilités des chemins qui atteignent chaque successeur"""
        if node.next_down is not None:
            node.next_down.reach_probability += node.reach_probability * node.proba_down
        if node.next_mid is not None:
            node.next_mid.reach_probability += node.reach_probability * node.proba_mid
        if node.next_up is not None:
            node.next_up.reach_probability += node.reach_probability * node.proba_up

    def _build_next_column(self, trunk: TrunkNode, step: int) -> TrunkNode:
        """On construit la colonne suivante et les connexions depuis la colonne actuelle"""
        next_price, _ = self._moments(trunk.price, step)
        if self.nb_next_nodes is NbNextNodes.BINOMIAL and step != self.div_step:

            if step % 2 == 0:
                next_price *= self.sqrt_alpha
            else:
                next_price /= self.sqrt_alpha

        next_trunk = TrunkNode(next_price, trunk)
        node = trunk.top()
        candidate = next_trunk
        # On parcourt toute la colonne actuelle, du prix le plus haut au plus bas
        while node is not None:
            candidate = self._connect(node, candidate, step)
            self._propagate_probability(node)
            node = node.down_node
        return next_trunk

    def build_tree(self) -> TrunkNode:
        """On construit l’arbre depuis la racine jusqu’à la dernière date"""

        self.root = TrunkNode(self.mkt.s0)
        self.root.reach_probability = 1.0
        self.last_trunk = None
        trunk = self.root

        for step in range(self.nb_steps):
            trunk = self._build_next_column(trunk, step)
        self.last_trunk = trunk
        return trunk

    def _price_node(self, node: Node, option: OptionTrade) -> None:
        """On actualise les valeurs suivantes et on applique la règle d’exercice du contrat"""
        # On fait la moyenne pondérée des valeurs futures, déjà calculées à ce stade
        continuation = 0.0
        if node.next_down is not None:
            continuation += node.proba_down * node.next_down.option_value
        if node.next_up is not None:
            continuation += node.proba_up * node.next_up.option_value
        if node.next_mid is not None:

            continuation += node.proba_mid * node.next_mid.option_value
        # On actualise la moyenne. Pour une américaine, on la compare à l'exercice immédiat
        node.option_value = option.node_value(self.df * continuation, node.price)

    def price(self, option: OptionTrade) -> float:
        """On remonte les payoffs terminaux pour obtenir le prix de l’option à la racine"""
        if not math.isclose(option.maturity, self.maturity, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("L'option et l'arbre doivent avoir la même maturité.")
        if self.last_trunk is None:
            self.build_tree()

        node = self.last_trunk.top()
        while node is not None:
            node.option_value = option.payoff(node.price)
            node = node.down_node

        trunk = self.last_trunk.prev_mid
        while trunk is not None:

            node = trunk.top()
            while node is not None:
                self._price_node(node, option)
                node = node.down_node
            trunk = trunk.prev_mid

        return self.root.option_value
