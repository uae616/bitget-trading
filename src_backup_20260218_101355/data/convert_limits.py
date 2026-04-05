from ..utils.symbols import pair_key

def build_convert_limits() -> dict:
    \"\"\"
    Placeholder defaults.
    Convert API access is sometimes restricted; this keeps the bot functional.
    You can replace this with real fetching later (convert exchangeInfo/assetInfo).
    \"\"\"
    return {
        pair_key('BTC','USDT'): {'min_notional': 1.0, 'precision': 8},
        pair_key('ETH','USDT'): {'min_notional': 1.0, 'precision': 8},
        pair_key('SOL','USDT'): {'min_notional': 1.0, 'precision': 6},
    }
