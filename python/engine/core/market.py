"""Market data entered by the user."""

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
        """Collecting market data and verifying their values"""

        self.s0 = s0
        self.int_rate = int_rate
        self.volatility = volatility
        # A % return is distinguished from a dividend paid on a specific date.
        self.div_yield = div_yield
        self.div_amount = div_amount
        self.t_ex_div = t_ex_div
        self._validate()

    def _validate(self) -> None:
        """Monitoring spot, volatility and dividend consistency"""
        values = (self.s0, self.int_rate, self.volatility, self.div_yield, self.div_amount)
        # Stop calculation if an input contains infinity or a value NaN
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Les données de marché doivent être finies.")

        if self.s0 <= 0 or self.volatility <= 0 or self.div_amount < 0:
            raise ValueError("Il faut S0 > 0, volatilité > 0 et dividende >= 0.")
        if self.t_ex_div is not None:
            if not math.isfinite(self.t_ex_div) or self.t_ex_div <= 0:
                raise ValueError("La date du dividende doit être positive et finie.")

        if self.div_amount > 0 and self.t_ex_div is None:
            raise ValueError("Il manque la date du dividende discret.")
