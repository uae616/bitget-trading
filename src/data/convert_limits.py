from ..utils.symbols import pair_key

def _to_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _default_limits(coins=None, quote_asset: str = 'USDT') -> dict:
    selected = [c.upper() for c in (coins or ['BTC', 'ETH', 'SOL'])]
    base = {
        'BTC': {'min_notional': 1.0, 'precision': 8},
        'ETH': {'min_notional': 1.0, 'precision': 8},
        'SOL': {'min_notional': 1.0, 'precision': 6},
    }

    out = {}
    for coin in selected:
        item = base.get(coin, {'min_notional': 1.0, 'precision': 8})
        out[pair_key(coin, quote_asset)] = {
            'min_notional': float(item['min_notional']),
            'precision': int(item['precision']),
        }
    return out


def build_convert_limits(convert_api=None, coins=None, quote_asset: str = 'USDT') -> dict:
    """
    Build convert limits from Binance Convert endpoints when available,
    with safe defaults fallback when API access is missing/restricted.
    """
    quote = str(quote_asset or 'USDT').upper()
    selected = [c.upper() for c in (coins or ['BTC', 'ETH', 'SOL'])]
    limits = _default_limits(selected, quote)

    if convert_api is None:
        return limits

    try:
        exch = convert_api.exchange_info() or {}
        asset = convert_api.asset_info() or {}
    except Exception:
        return limits

    asset_precision = {}
    if isinstance(asset, list):
        asset_rows = asset
    else:
        asset_rows = asset.get('list') or asset.get('data') or asset.get('assets') or []
    if isinstance(asset_rows, list):
        for row in asset_rows:
            coin = str(row.get('asset') or row.get('fromAsset') or '').upper()
            if not coin:
                continue
            p = row.get('fraction')
            if p is None:
                p = row.get('precision')
            if p is None:
                p = row.get('scale')
            try:
                asset_precision[coin] = int(p)
            except Exception:
                pass

    if isinstance(exch, list):
        rows = exch
    else:
        rows = exch.get('list') or exch.get('data') or exch.get('symbols') or []
    if not isinstance(rows, list):
        return limits

    for row in rows:
        from_asset = str(row.get('fromAsset') or '').upper()
        to_asset = str(row.get('toAsset') or '').upper()
        if from_asset not in selected or to_asset != quote:
            continue

        min_notional = None
        for k in ('fromAssetMinAmount', 'minFromAmount', 'fromMinAmount', 'minAmount', 'minQty'):
            min_notional = _to_float(row.get(k))
            if min_notional is not None and min_notional > 0:
                break

        pk = pair_key(from_asset, quote)
        current = limits.get(pk, {'min_notional': 1.0, 'precision': 8})
        limits[pk] = {
            'min_notional': float(min_notional) if (min_notional is not None and min_notional > 0) else float(current['min_notional']),
            'precision': int(asset_precision.get(from_asset, current['precision'])),
        }

    return limits

