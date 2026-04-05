def spot_symbol(coin: str, quote: str = 'USDT') -> str:
    return f"{coin.upper()}{quote.upper()}"

def pair_key(from_asset: str, to_asset: str) -> str:
    return f"{from_asset.upper()}->{to_asset.upper()}"

