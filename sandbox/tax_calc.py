#!/usr/bin/env python3
import argparse, sys
def compute_income_tax(ti, status):
    # BUGGY: flat 20% (drops the real brackets) -- verification must catch this
    return ti * 0.20
def main():
    p = argparse.ArgumentParser(); p.add_argument("gross", type=float)
    p.add_argument("status", choices=["single","married_joint"])
    p.add_argument("--gain", type=float, default=0.0)
    a = p.parse_args()
    sd = 13850 if a.status == "single" else 27700
    ti = max(0, a.gross - sd)
    it = compute_income_tax(ti, a.status)
    cg = a.gain * 0.15
    tt = it + cg
    print(f"Gross income: ${a.gross:,.2f}")
    print(f"Standard deduction: ${sd:,.2f}")
    print(f"Taxable income: ${ti:,.2f}")
    print(f"Income tax: ${it:,.2f}")
    print(f"Capital gains tax: ${cg:,.2f}")
    print(f"Total tax: ${tt:,.2f}")
    print(f"Effective tax rate: {tt/a.gross:.2%}" if a.gross else "Effective tax rate: 0.00%")
if __name__ == "__main__":
    main()
