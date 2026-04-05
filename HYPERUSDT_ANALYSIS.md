================================================================================
HYPERUSDT EXCLUSION ANALYSIS - Unified Scanner
================================================================================

QUESTION: Why did the scanner not generate a signal for HYPERUSDT?
ANSWER:   HYPERUSDT ranks #304 by volume, far below the top-18/20 selection.

================================================================================
1. TOP-N SELECTION (Default: 20)
================================================================================

FILE: src/unified_scanner/dashboard.py:1101
    p.add_argument("--top", type=int, default=20, help="Scan top N symbols...")

FILE: src/unified_scanner/main.py:534
    p.add_argument("--top", type=int, default=None, ...)

Dashboard: default top 20
CLI: requires explicit --top flag

================================================================================
2. SYMBOL SELECTION LOGIC
================================================================================

Function: _fetch_top_symbols()
Location 1: src/unified_scanner/main.py:113-128
Location 2: src/unified_scanner/dashboard.py:364-381

FLOW:
1. Fetch all ticker symbols from exchange
2. FILTER: Keep only symbols ending in "/{QUOTE}" (e.g., "/USDT")
3. Extract base (e.g., "BTC" from "BTC/USDT")
4. SORT: By quoteVolume (24h trading volume) descending
5. SELECT: Take top N symbols
6. FILTER: Remove stablecoins (_STABLE_BASES)
7. RETURN: Remaining symbols

CODE (main.py:118-123):
    if market == "futures":
        if not sym.endswith(f"/{quote.upper()}:{quote.upper()}"):
            continue
    else:
        if not sym.endswith(f"/{quote.upper()}"):  # SPOT: /USDT only
            continue

STABLECOIN FILTERING (main.py:41-43):
_STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "USDE", "USD1", "PYUSD"
}

================================================================================
3. HYPERUSDT VOLUME RANKING
================================================================================

Binance Spot Top 20 Symbols:
 1. BTC               2,116,761,479 USDT   <- TOP 1
 2. ETH               1,384,742,235 USDT
 3. USDC             (1,299,998,973) [FILTERED - stablecoin]
 4. NIGHT               776,409,341 USDT
 5. SOL                 422,907,347 USDT
 6. PAXG                401,912,675 USDT
 7. XRP                 250,304,789 USDT
 8. BNB                 169,508,901 USDT
 9. USD1              (156,545,225) [FILTERED - stablecoin]
10. DOGE                102,102,862 USDT
11. TAO                  88,350,706 USDT
12. ZEC                  65,776,182 USDT
13. TRX                  56,673,826 USDT
14. LINK                 56,405,299 USDT
15. ADA                  54,875,699 USDT
16. FDUSD              (48,538,595) [FILTERED - stablecoin]
17. EUR                  47,844,858 USDT
18. PEPE                 47,442,543 USDT  <- TOP 18 CUTOFF
19. SUI                  45,747,293 USDT
20. AVAX                 29,478,137 USDT  <- TOP 20 CUTOFF

HYPERUSDT:
- Rank: #304 by 24h volume
- Volume: 602,496 USDT
- Percentage of BTC: 0.028% (602K vs 2.1B)

RESULT:
15 non-stablecoin symbols from top-20 scan

================================================================================
4. WHY HYPERUSDT WAS EXCLUDED
================================================================================

EXCLUSION POINT: Volume Ranking (Step 1)
- HYPER volume: 602,496 USDT/24h
- Top 20 volumes: 29M to 2.1B USDT/24h
- HYPER ranks #304, selected cutoff is 20
- HYPER excluded BEFORE stablecoin filter check

DOES NOT APPLY:
1. Stablecoin check: HYPER not in _STABLE_BASES ✓
2. Exchange availability: HYPER/USDT pair exists ✓
3. Quote asset filtering: matches /USDT pattern ✓
4. Market type filtering: trading on spot market ✓

================================================================================
5. ADDRESSING YOUR QUESTIONS
================================================================================

Q1: Why no signal for HYPERUSDT?
A:  Not included in top-20 (default) or top-18 selection.
    Ranks #304 by 24h volume (602K USDT).
    Falls below any reasonable top-N cutoff.

Q2: Was it excluded from top-18 when 18 was chosen?
A:  YES. Top-18 selection takes ranks 1-18 by volume.
    HYPER is rank #304.
    Would be excluded with top-20 as well.

Q3: Why was it excluded?
A:  Low trading volume (602K USDT/day).
    Scanner prioritizes high-volume pairs for:
    - More reliable price data
    - Better liquidity for signals
    - Less noisy/pump-and-dump altcoins

Q4: Why top-18 instead of top-20?
A:  Currently DEFAULT is 20 (dashboard.py:1101)
    If user ran: python -m src.unified_scanner.dashboard --top 18
    Then top-18 would be selected
    Not configured in config.toml; CLI argument only

Q5: How exactly is top-N set?
A:  Dashboard (default): --top 20
    Main scanner: requires explicit --top N flag
    Not in config.toml
    Changed via command-line argument

================================================================================
6. FILE LOCATIONS
================================================================================

TOP-N SELECTION:
- src/unified_scanner/main.py:113-128
  Function: _fetch_top_symbols(exchange, quote, top_n, market)

- src/unified_scanner/dashboard.py:364-381
  Function: _fetch_top_symbols(exchange, quote, top_n, fallback)

ARGUMENT PARSING:
- src/unified_scanner/dashboard.py:1101
  CLI: --top (default=20)

- src/unified_scanner/main.py:534
  CLI: --top (default=None, optional)

STABLECOIN FILTERING:
- src/unified_scanner/main.py:41-43
- src/unified_scanner/dashboard.py:48-50

QUOTE ASSET FILTERING (hardcoded to USDT for spot):
- src/unified_scanner/main.py:122
- src/unified_scanner/dashboard.py:370

================================================================================
7. TO SCAN HYPERUSDT
================================================================================

Option 1: Explicit symbol
  python -m src.unified_scanner.main HYPER

Option 2: Add to config fallback
  In config.toml, add to [scanner] section:
    symbols = ["HYPER", "BTC", "ETH"]

Option 3: Increase top-N substantially (not recommended)
  python -m src.unified_scanner.dashboard --top 305
  (Requires HYPER to be in top 305, defeats filtering purpose)

================================================================================
CONCLUSION
================================================================================

HYPERUSDT does not generate scanner signals because:

1. It ranks #304 by 24h trading volume on Binance
2. Scanner defaults to top-20 symbols (or top-18 if explicitly set)
3. HYPER's volume (602K USDT) is 3000x lower than BTC (2.1B USDT)
4. No exclusion rule prevents HYPER; it's simply below the top-N cutoff
5. The filtering is INTENTIONAL: high-volume symbols generate better signals

This is working as designed, not a bug.

