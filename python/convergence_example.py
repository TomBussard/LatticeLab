"""Reproduce the European call convergence figure using the Python engine."""

from engine.service import calculate


def main():
    contract = {
        "valuation_date": "2026-01-01",
        "market": {"spot": 100, "rate": 0.05, "volatility": 0.20},
        "legs": [{"kind": "call", "strike": 100, "expiry": "2027-01-01"}],
        "greeks": [],
    }
    print("Steps   Binomial   Trinomial")
    for steps in (8, 12, 16, 24, 32, 48, 64, 96, 128, 192):
        values = [
            calculate({**contract, "grid": {"mode": mode, "steps": steps}})["price"]
            for mode in ("binomial", "trinomial")
        ]
        print(f"{steps:5d}   {values[0]:8.5f}   {values[1]:9.5f}")


if __name__ == "__main__":
    main()
