"""Données de marché saisies par l'utilisateur."""

import math


class Market:
    def __init__(
        self,
        s0: float,
        int_rate: float,
        volatility: float,
        div_yield: float = 0.0,
        div_amount: float = 0.0,
        t_ex_div: float | None = None,
    ) -> None:
        """On rassemble les données de marché et on vérifie leurs valeurs"""

        self.s0 = s0
        self.int_rate = int_rate
        self.volatility = volatility
        # On distingue un rendement en % d'un dividende versé à une date précise
        self.div_yield = div_yield
        self.div_amount = div_amount
        self.t_ex_div = t_ex_div
        self._validate()

    def _validate(self) -> None:
        """On contrôle la cohérence du spot, de la volatilité et du dividende"""
        values = (self.s0, self.int_rate, self.volatility,
                  self.div_yield, self.div_amount)
        # On arrête le calcul si une entrée contient l'infini ou une valeur NaN
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Les données de marché doivent être finies.")

        if self.s0 <= 0 or self.volatility <= 0 or self.div_amount < 0:
            raise ValueError("Il faut S0 > 0, volatilité > 0 et dividende >= 0.")
        if self.t_ex_div is not None:
            if not math.isfinite(self.t_ex_div) or self.t_ex_div <= 0:
                raise ValueError("La date du dividende doit être positive et finie.")

        if self.div_amount > 0 and self.t_ex_div is None:
            raise ValueError("Il manque la date du dividende discret.")
