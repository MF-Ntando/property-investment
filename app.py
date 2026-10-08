"""
Streamlit front end for property_engine.py
Every input starts EMPTY - the user must enter all values before analysing.
Run:  streamlit run app.py
"""
import pandas as pd
import streamlit as st

from property_engine import PropertyInput, analyse, WEIGHTS

st.set_page_config(page_title="Property Investment Analyser", page_icon="🏠", layout="wide")

st.title("🏠 Property Investment Analyser")
st.caption("Version 1 · South African residential property · pre-tax · "
           "results are model outputs based on YOUR assumptions, not financial advice.")


def R(x):
    return f"-R{abs(x):,.0f}" if x < 0 else f"R{x:,.0f}"


def pct(x):
    return "n/a" if x != x else f"{x * 100:.1f}%"


# ----------------------------------------------------------------------
# Cost mode sits outside the form so dependent fields can show/hide live
# ----------------------------------------------------------------------
st.subheader("1. Enter your property and assumptions")
st.info("All fields are required. There are no pre-filled values: enter 0 where "
        "something doesn't apply (e.g. levies on a freehold house).")

cost_mode = st.radio(
    "Bond & conveyancing costs",
    ["I will enter my own quotes", "Estimate them for me"],
    index=None,
    horizontal=True,
    help="Estimates are rough formulas. Real quotes from a bond originator/conveyancer are better.",
)

with st.form("inputs"):
    st.markdown("**Purchase & financing**")
    c1, c2, c3, c4 = st.columns(4)
    price = c1.number_input("Purchase price (R)", min_value=0.0, step=10_000.0, value=None, format="%.0f")
    deposit_pct = c2.number_input("Deposit (% of price)", min_value=0.0, max_value=99.0, step=1.0, value=None)
    interest = c3.number_input("Interest rate (% p.a.)", min_value=0.0, max_value=40.0, step=0.25, value=None)
    term = c4.number_input("Loan term (years)", min_value=1, max_value=30, step=1, value=None)

    bond_costs = conveyancing = None
    if cost_mode == "I will enter my own quotes":
        c1, c2, _, _ = st.columns(4)
        bond_costs = c1.number_input("Bond registration costs (R)", min_value=0.0, step=1_000.0, value=None, format="%.0f")
        conveyancing = c2.number_input("Conveyancing / transfer attorney fees (R)", min_value=0.0, step=1_000.0, value=None, format="%.0f")

    st.markdown("**Income & monthly costs**")
    c1, c2, c3, c4 = st.columns(4)
    rent = c1.number_input("Monthly rent (R)", min_value=0.0, step=500.0, value=None, format="%.0f")
    levies = c2.number_input("Levies (R/month)", min_value=0.0, step=100.0, value=None, format="%.0f")
    rates = c3.number_input("Rates & taxes (R/month)", min_value=0.0, step=100.0, value=None, format="%.0f")
    insurance = c4.number_input("Insurance (R/month)", min_value=0.0, step=50.0, value=None, format="%.0f")

    c1, c2, c3, _ = st.columns(4)
    maintenance = c1.number_input("Maintenance (% of rent)", min_value=0.0, max_value=100.0, step=1.0, value=None)
    vacancy = c2.number_input("Vacancy (% of year unrented)", min_value=0.0, max_value=100.0, step=1.0, value=None)
    mgmt = c3.number_input("Management fee (% of rent)", min_value=0.0, max_value=100.0, step=1.0, value=None,
                           help="Enter 0 if you self-manage.")

    st.markdown("**Growth & exit assumptions**")
    c1, c2, c3, c4, c5 = st.columns(5)
    rent_g = c1.number_input("Rent growth (% p.a.)", min_value=-20.0, max_value=30.0, step=0.5, value=None)
    exp_g = c2.number_input("Expense growth (% p.a.)", min_value=-20.0, max_value=30.0, step=0.5, value=None)
    appr = c3.number_input("Property growth (% p.a.)", min_value=-20.0, max_value=30.0, step=0.5, value=None)
    hold = c4.number_input("Holding period (years)", min_value=1, max_value=30, step=1, value=None)
    sell = c5.number_input("Selling costs (% of sale price)", min_value=0.0, max_value=30.0, step=0.5, value=None)

    submitted = st.form_submit_button("Analyse property", type="primary")

# ----------------------------------------------------------------------
# Validation: nothing runs until every required field is filled
# ----------------------------------------------------------------------
if not submitted:
    st.stop()

required = {
    "Purchase price": price, "Deposit": deposit_pct, "Interest rate": interest,
    "Loan term": term, "Monthly rent": rent, "Levies": levies, "Rates & taxes": rates,
    "Insurance": insurance, "Maintenance": maintenance, "Vacancy": vacancy,
    "Management fee": mgmt, "Rent growth": rent_g, "Expense growth": exp_g,
    "Property growth": appr, "Holding period": hold, "Selling costs": sell,
}
if cost_mode is None:
    st.error("Please choose how bond & conveyancing costs should be handled.")
    st.stop()
if cost_mode == "I will enter my own quotes":
    required["Bond registration costs"] = bond_costs
    required["Conveyancing fees"] = conveyancing

missing = [k for k, v in required.items() if v is None]
if missing:
    st.error("Please fill in every field. Missing: " + ", ".join(missing))
    st.stop()

problems = []
if price <= 0:
    problems.append("Purchase price must be greater than 0.")
if rent <= 0:
    problems.append("Monthly rent must be greater than 0.")
if hold > term:
    problems.append("Holding period cannot be longer than the loan term.")
if problems:
    for msg in problems:
        st.error(msg)
    st.stop()

# ----------------------------------------------------------------------
# Run the engine
# ----------------------------------------------------------------------
est = cost_mode == "Estimate them for me"
p = PropertyInput(
    price=price, monthly_rent=rent, deposit_pct=deposit_pct / 100,
    interest_rate=interest / 100, term_years=int(term),
    levies=levies, rates=rates, insurance=insurance,
    maintenance_pct_rent=maintenance / 100, vacancy_pct=vacancy / 100,
    management_pct=mgmt / 100, rent_growth=rent_g / 100,
    expense_growth=exp_g / 100, appreciation=appr / 100,
    hold_years=int(hold), selling_costs_pct=sell / 100,
    bond_costs=0.0 if est else bond_costs,
    conveyancing_costs=0.0 if est else conveyancing,
    use_estimated_costs=est,
)
a = analyse(p)
m, u, s, pr = a["monthly"], a["upfront"], a["score"], a["projection"]

st.divider()
st.subheader("2. Results")

# Score banner
score_msg = f"**Investment score: {s['score']}/100 — {s['label']}**"
if s["score"] >= 75:
    st.success(score_msg)
elif s["score"] >= 55:
    st.warning(score_msg)
else:
    st.error(score_msg)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Monthly cash flow (yr 1)", R(m["cash_flow"]))
k2.metric("Gross yield", pct(a["gross_yield"]))
k3.metric("Net yield", pct(a["net_yield"]))
k4.metric(f"{p.hold_years}-yr IRR", pct(pr["irr"]))

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cash needed up front", R(u["total_cash_needed"]))
k2.metric("Monthly bond", R(m["bond"]))
k3.metric(f"Net profit over {p.hold_years} yrs", R(pr["net_profit"]))
k4.metric("Cash-flow break-even price", R(a["breakeven_price"]))

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Monthly breakdown", "Scenarios", "What if I negotiate?", "Projection", "Score detail"])

with tab1:
    st.dataframe(pd.DataFrame({
        "Item": ["Rent after vacancy", "Management fee", "Maintenance", "Levies + rates + insurance",
                 "Net operating income", "Bond repayment", "Monthly cash flow"],
        "Amount": [R(m["collected_rent"]), R(-m["management"]), R(-m["maintenance"]),
                   R(-(p.levies + p.rates + p.insurance)), R(m["noi"]), R(-m["bond"]), R(m["cash_flow"])],
    }), hide_index=True, use_container_width=True)
    st.markdown("**Up-front costs**")
    st.dataframe(pd.DataFrame({
        "Item": ["Deposit", "Transfer duty", "Bond registration", "Conveyancing", "Total"],
        "Amount": [R(u["deposit"]), R(u["transfer_duty"]), R(u["bond_costs"]),
                   R(u["conveyancing"]), R(u["total_cash_needed"])],
    }), hide_index=True, use_container_width=True)
    st.caption("Transfer duty uses SARS brackets coded into the engine (from 1 April 2025). "
               "Verify against SARS; it does not apply to VAT-vendor purchases.")

with tab2:
    st.dataframe(pd.DataFrame([
        {"Scenario": n, "Monthly cash flow": R(v["monthly_cash_flow"]), f"{p.hold_years}-yr IRR": pct(v["irr"]),
         "Net profit": R(v["net_profit"]), "Equity multiple": f"{v['equity_multiple']:.2f}x"}
        for n, v in a["scenarios"].items()
    ]), hide_index=True, use_container_width=True)
    st.caption("Optimistic: rate −1.5pts, rent +7%, growth +8%, 3% vacancy. "
               "Stress: rate +2.5pts, rent +2%, growth 0%, 15% vacancy. "
               "These deltas are adjustable in property_engine.py.")

with tab3:
    st.dataframe(pd.DataFrame([
        {"Price": R(w["price"]), "Discount": f"{w['discount'] * 100:+.0f}%",
         "Monthly cash flow": R(w["cash_flow"]), "Net yield": pct(w["net_yield"])}
        for w in a["what_if"]
    ]), hide_index=True, use_container_width=True)
    if a["breakeven_price"] <= 0:
        st.write("No positive purchase price reaches break-even with these inputs.")
    else:
        st.write(f"Cash-flow break-even purchase price: **{R(a['breakeven_price'])}** "
                 f"({(a['breakeven_price'] / p.price - 1) * 100:+.0f}% vs your price), "
                 "holding rent and deposit % constant.")

with tab4:
    df = pd.DataFrame(pr["rows"]).set_index("year")
    st.line_chart(df[["value", "loan_balance", "equity_after_sale"]])
    st.caption("Property value, outstanding bond, and equity after selling costs.")
    show = df.rename(columns={
        "rent": "Monthly rent", "annual_cash_flow": "Annual cash flow", "value": "Property value",
        "loan_balance": "Loan balance", "equity_after_sale": "Equity after sale"})
    st.dataframe(show.style.format("R{:,.0f}"), use_container_width=True)

with tab5:
    st.dataframe(pd.DataFrame([
        {"Component": k.replace("_", " ").title(), "Score": f"{v}/100", "Weight": f"{WEIGHTS[k] * 100:.0f}%"}
        for k, v in s["components"].items()
    ]), hide_index=True, use_container_width=True)
    st.caption("The score is an analytical model of your stated assumptions, not an objective truth. "
               "Ranges and weights are set in property_engine.py.")
