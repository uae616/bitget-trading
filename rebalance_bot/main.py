"""
Entry-point for the Bitget Rebalance Bot.

Usage
-----
    python main.py [--dry-run] [--once]

Flags
-----
--dry-run   Compute and log orders without sending them to the exchange.
--once      Run the rebalance check once and exit (no scheduler loop).
"""

import argparse
import logging
import sys
import time

import schedule

import config
from bitget_client import BitgetClient
from rebalance import Rebalancer

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rebalance_bot")


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_rebalance(rebalancer: Rebalancer) -> None:
    logger.info("=== Rebalance check started ===")
    try:
        orders = rebalancer.run()
        if orders:
            logger.info("Executed %d rebalancing order(s).", len(orders))
        else:
            logger.info("No trades required.")
    except Exception as exc:
        logger.exception("Unexpected error during rebalance: %s", exc)
    logger.info("=== Rebalance check complete ===")


def build_rebalancer(dry_run: bool) -> Rebalancer:
    client = BitgetClient(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        passphrase=config.API_PASSPHRASE,
    )
    return Rebalancer(client=client, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bitget Portfolio Rebalance Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute orders but do not send them to the exchange.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no scheduler loop).",
    )
    args = parser.parse_args()

    rebalancer = build_rebalancer(dry_run=args.dry_run)

    if args.dry_run:
        logger.info("DRY-RUN mode enabled – no orders will be placed.")

    run_rebalance(rebalancer)

    if args.once:
        return

    interval = config.CHECK_INTERVAL_MINUTES
    logger.info("Scheduling rebalance every %d minute(s).", interval)
    schedule.every(interval).minutes.do(run_rebalance, rebalancer=rebalancer)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
