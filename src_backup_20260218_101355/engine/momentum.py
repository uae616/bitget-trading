def momentum_scores(prices_now: dict) -> dict:
    \"\"\"
    Placeholder momentum: returns 0 for all coins.
    Later you will replace with multi-horizon returns + z-score normalization.
    prices_now: {coin: price}
    \"\"\"
    return {k: 0.0 for k in prices_now.keys()}
