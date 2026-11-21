"""Binomial/trinomial tree of the price, with a discreet dividend."""

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
        """Projection factors and tree parameters are prepared"""
        self._validate_parameters(maturity, nb_steps, nb_next_nodes)
        self.mkt = mkt
        self.maturity = maturity
        self.nb_steps = nb_steps
        self.nb_next_nodes = nb_next_nodes
        # We can set 0 to disable trinomial pruning and keep the whole tree
        if not math.isfinite(pruning_threshold) or not 0.0 <= pruning_threshold < 1.0:
            raise ValueError("Le seuil d'élagage doit être compris entre 0 et 1 exclu.")
        self.pruning_threshold = pruning_threshold
        # The total duration is cut into N intervals of the same length
        self.time_step_year = maturity / nb_steps

        self.df = math.exp(-mkt.int_rate * self.time_step_year)
        self.fwd_proj = math.exp((mkt.int_rate - mkt.div_yield) * self.time_step_year)

        self.variance_factor = math.expm1(mkt.volatility**2 * self.time_step_year)
        self.sqrt_alpha, self.alpha = self._calculate_alpha()
        self.probas_no_div = self._calculate_proba_no_div()
        # Only once check the constant non-dividend probabilities
        Node(mkt.s0).set_probabilities(*self.probas_no_div)
        # We spot the step of the dividend once, before building the knots
        self.div_step = self._dividend_step()

        self.root: TrunkNode | None = None
        self.last_trunk: TrunkNode | None = None

    @staticmethod
    def _validate_parameters(maturity: float, nb_steps: int, mode: NbNextNodes) -> None:
        """Maturity, number of steps, and tree type are monitored"""
        if not math.isfinite(maturity) or maturity <= 0:
            raise ValueError("La maturité doit être positive et finie.")
        if type(nb_steps) is not int or nb_steps <= 0:
            raise ValueError("Le nombre de pas doit être un entier positif.")
        if not isinstance(mode, NbNextNodes):
            raise ValueError("Choisir NbNextNodes.BINOMIAL ou TRINOMIAL.")

    def _calculate_alpha(self) -> tuple[float, float]:
        """The multiplicative ratio between two nearby prices is calculated"""
        if self.nb_next_nodes is NbNextNodes.BINOMIAL:
            epsilon = self.variance_factor
            sqrt_alpha = 1.0 + epsilon / 2.0 + math.sqrt(epsilon * (1.0 + epsilon / 4.0))
            alpha = sqrt_alpha**2
        else:
            alpha = math.exp(self.mkt.volatility * math.sqrt(3.0 * self.time_step_year))
            sqrt_alpha = math.sqrt(alpha)
        if alpha <= 1.0:
            raise ValueError("Volatilité trop petite pour distinguer les nœuds de la grille.")
        return sqrt_alpha, alpha

    def _calculate_proba_no_div(self) -> tuple[float, float, float]:
        """Constant probability is calculated outside the dividend detachment"""
        if self.nb_next_nodes is NbNextNodes.BINOMIAL:
            up = 1.0 / (1.0 + self.sqrt_alpha)
            return 1.0 - up, 0.0, up
        alpha = self.alpha

        down = self.variance_factor / ((1.0 - alpha) * (alpha**-2 - 1.0))
        up = down / alpha
        return down, 1.0 - down - up, up

    def _dividend_step(self) -> int | None:
        """The step that contains the date of release of the dividend is identified"""
        date = self.mkt.t_ex_div

        if self.mkt.div_amount == 0 or date is None or date > self.maturity:
            return None
        position = date / self.time_step_year
        nearest = round(position)

        if math.isclose(position, nearest, rel_tol=0.0, abs_tol=1e-10):
            position = float(nearest)

        return max(0, math.ceil(position) - 1)

    def _moments(self, spot: float, step: int) -> tuple[float, float]:
        """The hope and variance of the following price are calculated taking into account the dividend"""

        expected = spot * self.fwd_proj
        adjusted_spot = spot
        if step == self.div_step:
            after_div = (step + 1) * self.time_step_year - self.mkt.t_ex_div
            after_div = max(0.0, after_div)
            drift = self.mkt.int_rate - self.mkt.div_yield
            # The projected dividend is withdrawn until the end of the step
            expected -= self.mkt.div_amount * math.exp(drift * after_div)

            adjusted_spot -= self.mkt.div_amount * after_div / self.time_step_year

        if expected <= 0:
            raise ValueError(
                f"Le dividende rend le forward négatif ou nul pour S={spot:.6g}. "
                "La grille positive du cours ne couvre pas ce cas."
            )
        # One returns a variance, so the square of a standard deviation
        variance = adjusted_spot**2 * self.fwd_proj**2 * self.variance_factor
        return expected, variance

    def _calculate_proba_with_div(
        self,
        expected: float,
        variance: float,
        middle: float,
        alpha: float | None = None,
    ) -> tuple[float, float, float]:
        """The probability is adjusted to the first two moments of the price after dividend"""
        alpha = self.alpha if alpha is None else alpha

        relative_gap = (expected - middle) / middle

        second_gap = variance / middle**2 + relative_gap * (expected / middle + 1.0)
        # The three equations are solved: weight sum, mean and second moment
        down = (second_gap - (alpha + 1.0) * relative_gap) / ((1.0 - alpha) * (alpha**-2 - 1.0))
        up = (relative_gap - (1.0 / alpha - 1.0) * down) / (alpha - 1.0)

        return down, 1.0 - down - up, up

    def _connect(self, node: Node, candidate: Node, step: int) -> Node:
        """A node is linked to the useful successors of the next column."""
        expected, variance = node.price * self.fwd_proj, 0.0
        if step == self.div_step:
            expected, variance = self._moments(node.price, step)

        if (
            self.nb_next_nodes is NbNextNodes.TRINOMIAL
            and node.reach_probability < self.pruning_threshold
        ):
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
            # The previously verified probabilities are re-used instead of being tested at each node
            node.proba_down, node.proba_mid, node.proba_up = self.probas_no_div
        return node.next_mid if trinomial else node.next_down

    def _dividend_branches(
        self, node: Node, expected: float, variance: float
    ) -> tuple[float, float, float]:
        """Dividend branches are expanded until usable probabilities are obtained"""
        probabilities = self._calculate_proba_with_div(expected, variance, node.next_mid.price)
        branch_alpha = self.alpha
        while probabilities[1] < 0.0 and min(probabilities[0], probabilities[2]) >= 0.0:
            node.next_up = node.next_up.upper(self.alpha)
            node.next_down = node.next_down.lower(self.alpha)
            branch_alpha *= self.alpha
            probabilities = self._calculate_proba_with_div(
                expected,
                variance,
                node.next_mid.price,
                branch_alpha,
            )
        return probabilities

    def _connect_pruned(self, node: Node, candidate: Node, expected: float) -> Node:
        """A very unlikely node is extended by a single central branch"""
        node.next_mid = candidate.closest(expected, self.alpha)

        node.proba_down, node.proba_mid, node.proba_up = 0.0, 1.0, 0.0
        return node.next_mid

    @staticmethod
    def _propagate_probability(node: Node) -> None:
        """Cumulative probabilities of paths that reach each successor"""
        if node.next_down is not None:
            node.next_down.reach_probability += node.reach_probability * node.proba_down
        if node.next_mid is not None:
            node.next_mid.reach_probability += node.reach_probability * node.proba_mid
        if node.next_up is not None:
            node.next_up.reach_probability += node.reach_probability * node.proba_up

    def _build_next_column(self, trunk: TrunkNode, step: int) -> TrunkNode:
        """The next column and connections are built from the current column"""
        next_price, _ = self._moments(trunk.price, step)
        if self.nb_next_nodes is NbNextNodes.BINOMIAL and step != self.div_step:
            if step % 2 == 0:
                next_price *= self.sqrt_alpha
            else:
                next_price /= self.sqrt_alpha

        next_trunk = TrunkNode(next_price, trunk)
        node = trunk.top()
        candidate = next_trunk
        # We go through the entire current column, from the highest to the lowest price
        while node is not None:
            candidate = self._connect(node, candidate, step)
            self._propagate_probability(node)
            node = node.down_node
        return next_trunk

    def build_tree(self) -> TrunkNode:
        """Tree is built from root to last date"""

        self.root = TrunkNode(self.mkt.s0)
        self.root.reach_probability = 1.0
        self.last_trunk = None
        trunk = self.root

        for step in range(self.nb_steps):
            trunk = self._build_next_column(trunk, step)
        self.last_trunk = trunk
        return trunk

    def _price_node(self, node: Node, option: OptionTrade) -> None:
        """The following values are updated and the contract exercise rule is applied:"""
        # The weighted average of future values, already calculated at this stage, is calculated.
        continuation = 0.0
        if node.next_down is not None:
            continuation += node.proba_down * node.next_down.option_value
        if node.next_up is not None:
            continuation += node.proba_up * node.next_up.option_value
        if node.next_mid is not None:
            continuation += node.proba_mid * node.next_mid.option_value
        # For an American, we compare it to the immediate exercise.
        node.option_value = option.node_value(self.df * continuation, node.price)

    def price(self, option: OptionTrade) -> float:
        """Pick up the terminal payoffs to get the option price at the root"""
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
