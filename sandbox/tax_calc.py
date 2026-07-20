#!/usr/bin/env python3
import argparse, sys
def compute_income_tax(ti, status):
    if status == "single":
        brackets = [(11000,0.10),(44725,0.12),(95375,0.22),(182100,0.24),(231250,0.32),(578125,0.35)]
    else:
        brackets = [(22000,0.10),(89450,0.12),(190750,0.22),(364200,0.24),(462500,0.32),(693750,0.35)]
    top = 0.37; tax = 0.0; prev = 0
    for lim, rate in brackets:
        if ti > lim:
            tax += (lim - prev) * rate; prev = lim
        else:
            tax += (ti - prev) * rate; return tax
    tax += (ti - prev) * top; return tax
def cap_gains_rate(ti, status):
    if status == "single":
        return 0.0 if ti <= 44625 else (0.15 if ti <= 492300 else 0.20)
    return 0.0 if ti <= 89350 else (0.15 if ti <= 553850 else 0.20)
def main():
    p = argparse.ArgumentParser(); p.add_argument("gross", type=float)
    p.add_argument("status", choices=["single","married_joint"])
    p.add_argument("--gain", type=float, default=0.0)
    a = p.parse_args()
    if a.gross < 0 or a.gain < 0:
        sys.exit("Error: values must be non-negative.")
    sd = 13850 if a.status == "single" else 27700
    ti = max(0, a.gross - sd)
    it = compute_income_tax(ti, a.status)
    cg = a.gain * cap_gains_rate(ti, a.status) if a.gain > 0 else 0.0
    tt = it + cg
    er = tt / a.gross if a.gross else 0.0
    print(f"Gross income: ${a.gross:,.2f}")
    print(f"Standard deduction: ${sd:,.2f}")
    print(f"Taxable income: ${ti:,.2f}")
    print(f"Income tax: ${it:,.2f}")
    print(f"Capital gains tax: ${cg:,.2f}")
    print(f"Total tax: ${tt:,.2f}")
    print(f"Effective tax rate: {er:.2%}")
if __name__ == "__main__":
    main()
