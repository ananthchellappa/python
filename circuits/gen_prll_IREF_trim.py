#!/usr/bin/env python3
import argparse

def format_resistance(value):
    """Return resistance nicely formatted in Ω, kΩ, or MΩ."""
    if value >= 1e6:
        return f"{value/1e6:.6g} MΩ"
    elif value >= 1e3:
        return f"{value/1e3:.6g} kΩ"
    else:
        return f"{value:.6g} Ω"

def main():
    parser = argparse.ArgumentParser(description="Calculate R_fixed, R_LSB, R_MSB from given parameters.")
    parser.add_argument("-VREF", type=float, default=0.5, help="Reference voltage (default 0.5V)")
    parser.add_argument("-INOM", type=float, default=5e-6, help="Nominal current (default 5 uA)")
    parser.add_argument("-N", type=int, default=5, help="Number of bits (default 5)")
    parser.add_argument("-PCT_LSB", type=float, default=2, help="Percentage LSB makes (default 2%)")

    args = parser.parse_args()

    # Extract parameters
    VREF = args.VREF
    INOM = args.INOM
    N = args.N
    PCT_LSB = args.PCT_LSB

    # Equations:
    R_LSB = VREF / (INOM * PCT_LSB / 100)
    R_MSB = R_LSB / (2 ** (N - 1))
    R_fixed = 1 / ((INOM / VREF) - (1 / R_MSB))

    print(f"VREF     = {VREF}")
    print(f"INOM     = {INOM}")
    print(f"N        = {N}")
    print(f"PCT_LSB  = {PCT_LSB}")
    print("---- Results ----")
    print(f"R_fixed  = {format_resistance(R_fixed)}")
    print(f"R_LSB    = {format_resistance(R_LSB)}")
    print(f"R_MSB    = {format_resistance(R_MSB)}")

if __name__ == "__main__":
    main()
