"""Contrat d'option, indépendant de la construction de l'arbre."""

import math


class OptionTrade:
    def __init__(
        self,
        strike: float,
        maturity: float,
        is_call: bool = True,
        is_american: bool = False,
    ) -> None:
        """On prépare le contrat avec son strike, sa maturité et son type d’exercice"""
        if not math.isfinite(strike) or strike < 0:
            raise ValueError("Le strike doit être positif ou nul et fini.")
        if not math.isfinite(maturity) or maturity <= 0:
            raise ValueError("La maturité doit être positive et finie.")
        self.strike = strike
        self.maturity = maturity
        self.is_call = is_call
        self.is_american = is_american

    def payoff(self, spot_price: float) -> float:
        """On calcule le paiement du call ou du put au prix indiqué"""

        if self.is_call:
            return max(spot_price - self.strike, 0.0)

        return max(self.strike - spot_price, 0.0)

    def node_value(self, continuation_value: float, spot_price: float) -> float:
        """On compare la continuation à l’exercice immédiat pour une option américaine"""
        # On compare ce que rapporte l'exercice avec la valeur obtenue en attendant
        if self.is_american:
            return max(continuation_value, self.payoff(spot_price))

        return continuation_value
