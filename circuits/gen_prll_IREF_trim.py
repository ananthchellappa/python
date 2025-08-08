#!/usr/bin/env python3
import argparse
import sys

def fmt_R(value):
    if value >= 1e6:
        return f"{value/1e6:.6g} MΩ"
    elif value >= 1e3:
        return f"{value/1e3:.6g} kΩ"
    else:
        return f"{value:.6g} Ω"

def fmt_I(value):
    if abs(value) >= 1:
        return f"{value:.6g} A"
    elif abs(value) >= 1e-3:
        return f"{value*1e3:.6g} mA"
    elif abs(value) >= 1e-6:
        return f"{value*1e6:.6g} µA"
    else:
        return f"{value*1e9:.6g} nA"

def main():
    p = argparse.ArgumentParser(
        description="Calculate R_fixed, R_LSB, R_MSB and trim range currents.",
        epilog=("Examples:\n"
                "  python3 script.py\n"
                "  python3 script.py -VREF 0.5 -INOM 6e-6 -N 4 -PCT_LSB 3"),
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("-VREF", type=float, default=0.5, help="Reference voltage (default 0.5V)")
    p.add_argument("-INOM", type=float, default=5e-6, help="Nominal current (default 5uA)")
    p.add_argument("-N", type=int, default=5, help="Number of bits (default 5)")
    p.add_argument("-PCT_LSB", type=float, default=2, help="Percentage LSB makes (default 2%)")
    a = p.parse_args()

    VREF, INOM, N, PCT_LSB = a.VREF, a.INOM, a.N, a.PCT_LSB

    # Core relations
    R_LSB = VREF / (INOM * (PCT_LSB / 100.0))
    R_MSB = R_LSB / (2 ** (N - 1))
    denom = (INOM / VREF) - (1.0 / R_MSB)
    if denom <= 0:
        sys.exit("Error: Inputs imply non-positive 1/R_fixed. "
                 "Try adjusting INOM, N, PCT_LSB, or VREF.")
    R_fixed = 1.0 / denom

    # Parallel network min R (all bits ON)
    R_min_inv = (1.0 / R_fixed) + ((2 ** N - 1) / R_LSB)
    R_min = 1.0 / R_min_inv

    # Currents and percentages
    IREF_max = VREF / R_min
    IREF_min = VREF / R_fixed
    IREF_max_PCT = (IREF_max - INOM) / INOM * 100.0
    IREF_min_PCT = (INOM - IREF_min) / INOM * 100.0

    # Total series sum of all resistors
    total_series_sum = R_fixed + sum(R_LSB / (2 ** k) for k in range(N))

    # Output
    print(f"VREF    = {VREF}")
    print(f"INOM    = {INOM}  ({fmt_I(INOM)})")
    print(f"N       = {N}")
    print(f"PCT_LSB = {PCT_LSB}%")
    print("---- Results ----")
    print(f"R_fixed         = {fmt_R(R_fixed)}")
    print(f"R_LSB           = {fmt_R(R_LSB)}")
    print(f"R_MSB           = {fmt_R(R_MSB)}")
    print("---- Trim Range ----")
    print(f"R_min           = {fmt_R(R_min)}  (all trim resistors ON in parallel)")
    print(f"IREF_max        = {fmt_I(IREF_max)}  (at R_min)")
    print(f"IREF_max_PCT    = {IREF_max_PCT:.4g}% greater than INOM")
    print(f"IREF_min        = {fmt_I(IREF_min)}  (only R_fixed path)")
    print(f"IREF_min_PCT    = {IREF_min_PCT:.4g}% less than INOM")
    print("---- Network Info ----")
    print(f"Total series sum= {fmt_R(total_series_sum)}  (R_fixed + R_LSB + R_LSB/2 + ... )")

if __name__ == "__main__":
    main()
