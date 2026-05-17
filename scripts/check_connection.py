"""Run this BEFORE trading. Connects to Quotex, proves the demo guard, prints
the account + balance, then disconnects. Places NO trades.

  python scripts/check_connection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_settings  # noqa: E402
from src.connector.quotex import QuotexConnector  # noqa: E402


def main() -> None:
    s = load_settings()
    if not s.email or not s.password:
        raise SystemExit("Set QUOTEX_EMAIL / QUOTEX_PASSWORD in .env first.")

    conn = QuotexConnector(s.email, s.password, allow_real=s.is_real)
    try:
        print("connecting (first run may take a while: Cloudflare/2FA)...")
        conn.connect()
        acct = "DEMO" if conn.is_demo else "REAL"
        print(f"\n  connected   : yes")
        print(f"  account     : {acct}")
        print(f"  is_demo     : {conn.is_demo}")
        print(f"  balance     : {conn.balance():.2f}")
        if conn.is_demo:
            print("\nDemo guard OK — safe to run scripts/run_live.py "
                  "--connector quotex")
        else:
            print("\nWARNING: live account is REAL.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
