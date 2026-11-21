# LatticeLab

LatticeLab prices equity options with binomial and trinomial trees in Python and Excel VBA. I wanted to see when it pays to exercise an American put early and how much a call’s hedge changes as the share price moves.

## Inside the pricer

Both examples use a share price and strike of **€100**, one year to expiry, **20%** annual volatility, a continuously compounded **5%** interest rate and no dividends. Each position is long one option on one share. The interface can also price contracts with a continuous dividend yield or one dated cash dividend.

### When is it worth exercising the put?

I started with a four-step American put so I could check each decision by hand. In the diagram, **S** is the share price and **V** is the put value. A darker outline marks a node where the holder exercises before expiry. The colour and size of each node show the risk-neutral probability of reaching it.

![Four-step American put in LatticeLab with share and option prices at all fifteen nodes](figures/american-put-tree.jpg)

I build each step around the share's forward value. Let $S$ be the current share price, $r$ the interest rate, $q$ the continuous dividend yield, $\sigma$ the volatility and $\Delta t$ the step length in years. For a binomial step with no cash dividend, I choose the larger solution $a>1$ below to match the one-step variance.

```math
F=S e^{(r-q)\Delta t}, \qquad a+a^{-1}=1+e^{\sigma^2\Delta t}
```

```math
S_u=Fa,\qquad S_d=F/a,\qquad p_u=\frac{1}{1+a}
```

From €100, a quarter-year step gives **€111.93** with probability **47.50%** and **€91.60** with probability **52.50%**. Their probability-weighted mean is the forward value, €101.26. Up-then-down and down-then-up meet at the same node, so both paths use the same exercise decision. [Branch construction](python/engine/core/tree.py)

| Decision | Share price | Exercise proceeds | Discounted value of waiting | Put value |
| --- | ---: | ---: | ---: | ---: |
| Today | €100.00 | €0.00 | €6.15 | €6.15 |
| After two down moves | €83.91 | €16.09 | €15.39 | €16.09 |

At expiry the put pays $V_T=\max(K-S_T,0)$ for strike $K$. At every earlier node I compare the proceeds from exercising with the discounted value of its two children.

```math
C=e^{-r\Delta t}\bigl[p_u V_u+(1-p_u)V_d\bigr],\qquad V=\max(K-S,C)
```

After two down moves, exercising is worth **€0.70 more** than waiting. Today the opposite decision wins. Carrying the child values back to the root gives **€6.1520**. To follow the same calculation in the app, open the example, choose **Tree**, click **Build tree** and expand **Show nodes**. [Four-step put inputs](examples/american-put.json)

### What happens to the hedge as the share moves?

For the European call I used 128 binomial steps. To estimate delta, the **Greeks** view prices the same contract twice, shifting the spot by $h$ in each direction.

```math
\Delta(S)\approx\frac{V(S+h)-V(S-h)}{2h}
```

At a spot of €100 the default bump is €2. The call is worth €9.21644 at €98 and €11.74949 at €102. Dividing the difference by €4 gives **0.6333 shares**. Expanding **Delta** repeats the calculation across nine spots with the strike, expiry, rate and volatility fixed. [Finite-difference calculation](python/engine/derivatives.py)

![Call delta by share price in the running Python application](figures/call-delta.jpg)

| Share price | €80 | €100 | €120 |
| --- | ---: | ---: | ---: |
| Call delta in shares | 0.2213 | 0.6333 | 0.8954 |

At the strike, one long call has roughly the same exposure to a small move as **0.63 shares**. A short position in that many shares offsets its initial delta. At €120 the hedge is closer to **0.90 shares**. Open the call example, choose **Greeks**, click **Calculate Greeks** and expand **Delta** to reproduce the curve. [128-step call inputs](examples/european-call.json)

### How fine does the grid need to be?

The European call has an analytical Black-Scholes price of **€10.450584**. Under **Convergence**, the app prices it on six grids and plots both the price and the absolute error. The dashed line in the lower panel marks the requested tolerance of €0.001.

![Six binomial prices and their absolute errors, plotted against grid size in LatticeLab](figures/binomial-convergence.jpg)

| Time steps | Binomial price | Absolute error |
| ---: | ---: | ---: |
| 8 | €10.642637 | €0.192054 |
| 32 | €10.490958 | €0.040374 |
| 64 | €10.421614 | €0.028970 |
| 96 | €10.458204 | €0.007621 |
| 128 | €10.464454 | €0.013870 |

The 64-step tree crosses below the reference, and the error at 128 steps is larger than at 96. None of these six grids reaches the requested tolerance. For comparison, the separate figure below runs both tree methods at ten grid sizes on the same market assumptions.

![Binomial and trinomial European call prices against the analytical reference across ten grids](figures/tree-convergence.png)

## How it works

The input layer normalises dates, day count, dividend schedules and signed positions. The pricing layer builds a recombining lattice, assigns option payoffs at expiry and works back through the tree. The analysis routines reuse those engines for prices, Greeks, tree inspection and convergence. The Excel bridge passes the same inputs to the workbook. [Inputs](python/engine/inputs.py) · [Tree construction](python/engine/core/tree.py) · [Pricing](python/engine/pricing.py) · [Analysis](python/analyses.py) · [Excel bridge](python/excel_bridge.py)

I checked the implementations separately from grid accuracy. For the 32-step European call the Python prices are **€10.490958** for the binomial tree and **€10.445273** for the trinomial tree. Desktop Excel agreed with Python to within **€0.000000000001** for both prices. The differences from Black-Scholes at this grid size are still visible.

## Run locally

From the repository root, start the local interface with Python 3.10 or later.

```sh
python python/server.py
```

In the **Market** sidebar, click **Open** and select either JSON file in the `examples` directory. The Python engine runs offline with the standard library. To print the ten-grid comparison directly, run `python python/convergence_example.py`.

For a side-by-side comparison, use desktop Excel on Windows, install the bridge with `python -m pip install -r requirements.txt`, then select **Python and VBA** in the app. [Excel workbook](vba/Pricer.xlsm) · [Exported VBA modules](vba)

Tom Bussard
