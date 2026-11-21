"""Option contract, independent of tree construction."""

import math


class OptionTrade:
    def __init__(
        self,
        strike: float,
        maturity: float,
        is_call: bool = True,
        is_american: bool = False,
    ) -> None:
        """We prepare the contract with its strike, maturity and type of exercise"""
        if not math.isfinite(strike) or strike < 0:
            raise ValueError("Le strike doit être positif ou nul et fini.")
        if not math.isfinite(maturity) or maturity <= 0:
            raise ValueError("La maturité doit être positive et finie.")
        self.strike = strike
        self.maturity = maturity
        self.is_call = is_call
        self.is_american = is_american

    def payoff(self, spot_price: float) -> float:
        """Payment of the call or put is calculated at the price indicated"""

        if self.is_call:
            return max(spot_price - self.strike, 0.0)

        return max(self.strike - spot_price, 0.0)

    def node_value(self, continuation_value: float, spot_price: float) -> float:
        """The continuation is compared to the immediate exercise for an American option"""
        # Comparisons are made between the exercise and the value obtained in the meantime
        if self.is_american:
            return max(continuation_value, self.payoff(spot_price))

        return continuation_value
