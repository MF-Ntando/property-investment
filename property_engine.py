"""
Property Investment Analysis Engine - Version 1
================================================
Deterministic financial model for South African residential property.
Pure standard library. Pre-tax. All assumptions are explicit inputs.

Pipeline:  inputs -> bond/cash flow -> yields -> 10-yr projection (IRR)
           -> scenarios -> break-even price -> investment score

Run:  python property_engine.py
"""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict


# ----------------------------------------------------------------------
# 1. INPUTS
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class PropertyInput:
    price: float
    monthly_rent: float
    deposit_pct: float = 0.10          # of price
    interest_rate: float = 0.105       # annual, nominal (PLACEHOLDER - use current rate)
    term_years: int = 20
    levies: float = 0.0                # R/month
    rates: float = 0.0                 # municipal rates & taxes, R/month
    insurance: float = 0.0             # R/month
    maintenance_pct_rent: float = 0.05 # % of rent set aside for repairs
    vacancy_pct: float = 0.05          # share of year unrented
    management_pct: float = 0.08       # % of collected rent (0 if self-managed)
    rent_growth: float = 0.05          # per year
    expense_growth: float = 0.06       # per year (levies, rates, insurance)
    appreciation: float = 0.05         # per year
    hold_years: int = 10
    selling_costs_pct: float = 0.06    # agent commission + VAT etc. on exit
    bond_costs: float = 0.0            # set None-like 0 to use estimate below
    conveyancing_costs: float = 0.0    # same
    use_estimated_costs: bool = True   # estimate bond/conveyancing if True


# ----------------------------------------------------------------------
# 2. CORE FORMULAS
# ----------------------------------------------------------------------
# SA transfer duty brackets (rates in force at time of writing, from 1 Apr 2025).
# VERIFY against SARS before relying on these - they change in the Budget.
# (lower bound, base duty, marginal rate)
TRANSFER_DUTY_BRACKETS = [
    (0,          0,         0.00),
    (1_210_000,  0,         0.03),
    (1_663_800,  13_614,    0.06),
    (2_329_300,  53_544,    0.08),
    (2_994_800,  106_784,   0.11),
    (13_310_000, 1_241_456, 0.13),
]


def transfer_duty(price: float) -> float:
    """Transfer duty for non-VAT residential purchases."""
    lower, base, rate = TRANSFER_DUTY_BRACKETS[0]
    for lo, b, r in TRANSFER_DUTY_BRACKETS:
        if price > lo:
            lower, base, rate = lo, b, r
    return base + (price - lower) * rate


def monthly_bond_payment(loan: float, annual_rate: float, years: int) -> float:
    """Standard annuity (PMT) with monthly compounding."""
    n = years * 12
    r = annual_rate / 12
    if loan <= 0:
        return 0.0
    if r == 0:
        return loan / n
    return loan * r / (1 - (1 + r) ** -n)


def loan_balance(loan: float, annual_rate: float, years: int, months_paid: int) -> float:
    r = annual_rate / 12
    pmt = monthly_bond_payment(loan, annual_rate, years)
    if r == 0:
        return max(loan - pmt * months_paid, 0.0)
    return max(loan * (1 + r) ** months_paid - pmt * ((1 + r) ** months_paid - 1) / r, 0.0)


def upfront_costs(p: PropertyInput) -> dict:
    loan = p.price * (1 - p.deposit_pct)
    if p.use_estimated_costs:
        # Rough estimates only - replace with real quotes.
        bond = 0.012 * loan + 6_000 if loan > 0 else 0.0
        conv = 0.008 * p.price + 8_000
    else:
        bond, conv = p.bond_costs, p.conveyancing_costs
    duty = transfer_duty(p.price)
    deposit = p.price * p.deposit_pct
    return {
        "deposit": deposit,
        "transfer_duty": duty,
        "bond_costs": bond,
        "conveyancing": conv,
        "total_cash_needed": deposit + duty + bond + conv,
    }


def monthly_breakdown(p: PropertyInput) -> dict:
    loan = p.price * (1 - p.deposit_pct)
    bond = monthly_bond_payment(loan, p.interest_rate, p.term_years)
    collected = p.monthly_rent * (1 - p.vacancy_pct)
    mgmt = collected * p.management_pct
    maint = p.monthly_rent * p.maintenance_pct_rent
    opex = p.levies + p.rates + p.insurance + maint + mgmt   # excludes bond
    noi = collected - opex                                    # net operating income
    return {
        "loan": loan, "bond": bond, "collected_rent": collected,
        "management": mgmt, "maintenance": maint, "operating_expenses": opex,
        "noi": noi, "cash_flow": noi - bond,
    }


def gross_yield(p: PropertyInput) -> float:
    return p.monthly_rent * 12 / p.price


def net_yield(p: PropertyInput) -> float:
    return monthly_breakdown(p)["noi"] * 12 / p.price


def irr(cash_flows: list[float]) -> float:
    """IRR by bisection (annual flows). Returns nan if no sign change."""
    def npv(rate): return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))
    lo, hi = -0.99, 5.0
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ----------------------------------------------------------------------
# 3. MULTI-YEAR PROJECTION
# ----------------------------------------------------------------------
def project(p: PropertyInput) -> dict:
    loan = p.price * (1 - p.deposit_pct)
    bond_m = monthly_bond_payment(loan, p.interest_rate, p.term_years)
    cash_in = upfront_costs(p)["total_cash_needed"]
    flows = [-cash_in]
    rows = []
    for yr in range(1, p.hold_years + 1):
        g_rent = (1 + p.rent_growth) ** (yr - 1)
        g_exp = (1 + p.expense_growth) ** (yr - 1)
        rent = p.monthly_rent * g_rent
        collected = rent * (1 - p.vacancy_pct)
        opex = ((p.levies + p.rates + p.insurance) * g_exp
                + rent * p.maintenance_pct_rent
                + collected * p.management_pct)
        annual_cf = (collected - opex - bond_m) * 12
        value = p.price * (1 + p.appreciation) ** yr
        bal = loan_balance(loan, p.interest_rate, p.term_years, yr * 12)
        net_sale = value * (1 - p.selling_costs_pct) - bal
        rows.append({"year": yr, "rent": rent, "annual_cash_flow": annual_cf,
                     "value": value, "loan_balance": bal, "equity_after_sale": net_sale})
        flows.append(annual_cf)
    flows[-1] += rows[-1]["equity_after_sale"]
    total_in = cash_in - sum(r["annual_cash_flow"] for r in rows if r["annual_cash_flow"] < 0)
    total_back = (sum(r["annual_cash_flow"] for r in rows if r["annual_cash_flow"] > 0)
                  + rows[-1]["equity_after_sale"])
    return {
        "rows": rows, "irr": irr(flows), "cash_invested": cash_in,
        "equity_multiple": total_back / total_in if total_in > 0 else float("nan"),
        "net_profit": sum(r["annual_cash_flow"] for r in rows)
                      + rows[-1]["equity_after_sale"] - cash_in,
    }


# ----------------------------------------------------------------------
# 4. SCENARIOS & BREAK-EVEN
# ----------------------------------------------------------------------
SCENARIOS = {
    "Optimistic": dict(interest_rate_delta=-0.015, rent_growth=0.07, appreciation=0.08, vacancy_pct=0.03),
    "Expected":   dict(interest_rate_delta=0.0,    rent_growth=None, appreciation=None, vacancy_pct=None),
    "Stress":     dict(interest_rate_delta=+0.025, rent_growth=0.02, appreciation=0.00, vacancy_pct=0.15),
}


def apply_scenario(p: PropertyInput, spec: dict) -> PropertyInput:
    changes = {"interest_rate": p.interest_rate + spec["interest_rate_delta"]}
    for k in ("rent_growth", "appreciation", "vacancy_pct"):
        if spec[k] is not None:
            changes[k] = spec[k]
    return replace(p, **changes)


def run_scenarios(p: PropertyInput) -> dict:
    out = {}
    for name, spec in SCENARIOS.items():
        sp = apply_scenario(p, spec)
        proj = project(sp)
        out[name] = {"monthly_cash_flow": monthly_breakdown(sp)["cash_flow"],
                     "irr": proj["irr"], "net_profit": proj["net_profit"],
                     "equity_multiple": proj["equity_multiple"]}
    return out


def breakeven_price(p: PropertyInput) -> float:
    """Purchase price at which month-1 cash flow = 0 (rent & deposit % held constant)."""
    def cf(price): return monthly_breakdown(replace(p, price=price))["cash_flow"]
    lo, hi = 1.0, p.price * 5
    if cf(lo) < 0:
        return 0.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if cf(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return lo


def what_if_prices(p: PropertyInput, steps=(0.0, -0.05, -0.10, -0.15)) -> list[dict]:
    rows = []
    for s in steps:
        price = p.price * (1 + s)
        q = replace(p, price=price)
        rows.append({"price": price, "discount": s,
                     "cash_flow": monthly_breakdown(q)["cash_flow"],
                     "net_yield": net_yield(q)})
    return rows


# ----------------------------------------------------------------------
# 5. SCORING  (a model on stated assumptions - not objective truth)
# ----------------------------------------------------------------------
def _scale(x: float, lo: float, hi: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


WEIGHTS = {"yield": 0.30, "cash_flow": 0.25, "return": 0.30, "resilience": 0.15}


def investment_score(p: PropertyInput) -> dict:
    mb = monthly_breakdown(p)
    proj = project(p)
    stress = run_scenarios(p)["Stress"]
    parts = {
        "yield":      _scale(net_yield(p), 0.03, 0.09),
        "cash_flow":  _scale(mb["cash_flow"] / p.monthly_rent, -0.30, 0.10),
        "return":     _scale(proj["irr"], 0.00, 0.15),
        "resilience": _scale(stress["monthly_cash_flow"] / p.monthly_rent, -0.60, 0.0),
    }
    total = sum(parts[k] * WEIGHTS[k] for k in parts)
    label = "Strong candidate" if total >= 75 else "Moderate - investigate" if total >= 55 else "High risk"
    return {"score": round(total), "label": label, "components": {k: round(v) for k, v in parts.items()}}


# ----------------------------------------------------------------------
# 6. REPORT
# ----------------------------------------------------------------------
def R(x: float) -> str:
    return f"-R{abs(x):,.0f}" if x < 0 else f"R{x:,.0f}"


def pct(x: float) -> str:
    return "n/a" if x != x else f"{x * 100:.1f}%"


def analyse(p: PropertyInput) -> dict:
    return {
        "upfront": upfront_costs(p), "monthly": monthly_breakdown(p),
        "gross_yield": gross_yield(p), "net_yield": net_yield(p),
        "projection": project(p), "scenarios": run_scenarios(p),
        "breakeven_price": breakeven_price(p), "what_if": what_if_prices(p),
        "score": investment_score(p),
    }


def print_report(p: PropertyInput, title: str = "PROPERTY INVESTMENT ANALYSIS") -> None:
    a = analyse(p)
    m, u, s = a["monthly"], a["upfront"], a["score"]
    line = "-" * 56
    print(f"\n{title}\n{'=' * 56}")
    print(f"Price {R(p.price)} | Rent {R(p.monthly_rent)}/m | Deposit {pct(p.deposit_pct)} "
          f"| Rate {pct(p.interest_rate)} | {p.term_years}y")
    print(f"\n{line}\nCASH NEEDED UP FRONT\n{line}")
    for k in ("deposit", "transfer_duty", "bond_costs", "conveyancing", "total_cash_needed"):
        print(f"  {k.replace('_', ' ').title():<22}{R(u[k]):>14}")
    print(f"\n{line}\nMONTHLY (YEAR 1)\n{line}")
    for k, lbl in [("collected_rent", "Rent after vacancy"), ("operating_expenses", "Operating expenses"),
                   ("noi", "Net operating income"), ("bond", "Bond repayment"), ("cash_flow", "CASH FLOW")]:
        print(f"  {lbl:<22}{R(m[k]):>14}")
    print(f"\n  Gross yield {pct(a['gross_yield'])}   Net yield {pct(a['net_yield'])}")
    pr = a["projection"]
    print(f"\n{line}\n{p.hold_years}-YEAR OUTLOOK (expected case)\n{line}")
    print(f"  IRR {pct(pr['irr'])}   Net profit {R(pr['net_profit'])}   "
          f"Equity multiple {pr['equity_multiple']:.2f}x")
    print(f"\n{line}\nSCENARIOS\n{line}")
    print(f"  {'Scenario':<12}{'Cash flow/m':>14}{'IRR':>9}{'Net profit':>16}")
    for n, v in a["scenarios"].items():
        print(f"  {n:<12}{R(v['monthly_cash_flow']):>14}{pct(v['irr']):>9}{R(v['net_profit']):>16}")
    print(f"\n{line}\nWHAT IF I NEGOTIATE?\n{line}")
    for w in a["what_if"]:
        print(f"  {R(w['price']):>12} ({w['discount'] * 100:+.0f}%)  cash flow {R(w['cash_flow']):>9}"
              f"  net yield {pct(w['net_yield'])}")
    print(f"\n  Cash-flow break-even price: {R(a['breakeven_price'])}")
    print(f"\n{line}\nINVESTMENT SCORE: {s['score']}/100 - {s['label']}\n{line}")
    for k, v in s["components"].items():
        print(f"  {k.replace('_', ' ').title():<14}{v:>4}/100  (weight {WEIGHTS[k] * 100:.0f}%)")
    print("\n  Model output based on the stated assumptions; not financial advice.")


# ----------------------------------------------------------------------
# 7. SELF-TESTS & DEMO
# ----------------------------------------------------------------------
def _selftest() -> None:
    assert abs(monthly_bond_payment(1_000_000, 0.12, 20) - 11_010.86) < 1
    assert transfer_duty(1_000_000) == 0
    assert abs(transfer_duty(1_500_000) - (1_500_000 - 1_210_000) * 0.03) < 1e-6
    assert abs(loan_balance(1_000_000, 0.12, 20, 240)) < 1
    assert abs(irr([-100, 110]) - 0.10) < 1e-6
    p = PropertyInput(price=1_250_000, monthly_rent=10_500, levies=1_300, rates=600, insurance=250)
    be = breakeven_price(p)
    assert abs(monthly_breakdown(replace(p, price=be))["cash_flow"]) < 1
    print("self-tests passed")


if __name__ == "__main__":
    _selftest()
    demo = PropertyInput(
        price=1_250_000, monthly_rent=10_500,
        levies=1_300, rates=600, insurance=250,
    )
    print_report(demo, "DEMO: R1.25m APARTMENT")
