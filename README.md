# LatticeLab

LatticeLab prices the same option in Python and Excel VBA. The side-by-side view makes it possible to tell whether a difference comes from the tree resolution, the contract terms or the implementation.

## Try an experiment

Start with a European call and refine the binomial grid. Compare its price with the trinomial result. Then switch to an American put, introduce a discrete dividend and inspect how the exercise decision and hedge change. The interface also supports digital payoffs, portfolios of signed positions and sensitivity analysis.

## How it works

The chart uses a one-year European call with spot and strike at 100, volatility at 20 percent, a 5 percent interest rate and zero dividends. An analytical value of 10.4506 provides a check on both tree methods.

![Binomial and trinomial call prices at ten grid sizes against the analytical reference](figures/tree-convergence.png)

The market, option, node and tree are separate objects. The engines build a recombining tree and roll the payoff back to the valuation date. The local web interface sends the same market and contract parameters to each engine. The Python sources are in `python/engine`. The Excel implementation includes the workbook and its exported VBA modules in `vba`.

## Run locally

The Python engine needs Python 3.10 or later. From the repository root, run the following command.

```sh
python python/server.py
```

For the Excel comparison, use desktop Excel on Windows and install the bridge with `python -m pip install -r requirements.txt`. The workbook is [Pricer.xlsm](vba/Pricer.xlsm). Its [VBA modules](vba) can be read directly on GitHub.

Portfolio by **Tom Bussard** at Université Paris Dauphine PSL, November 2026.
