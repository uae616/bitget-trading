def build_spot_filters(exchange_info: dict) -> dict:
    \"\"\"
    Returns: { 'BTCUSDT': {'min_notional': float, 'step_size': float, 'min_qty': float} }
    \"\"\"
    out = {}
    for s in exchange_info.get('symbols', []):
        symbol = s.get('symbol')
        filters = {f.get('filterType'): f for f in s.get('filters', [])}

        lot = filters.get('LOT_SIZE', {})
        step = float(lot.get('stepSize', '0') or 0)
        min_qty = float(lot.get('minQty', '0') or 0)

        # Binance may use NOTIONAL or MIN_NOTIONAL depending on doc version.
        notional = filters.get('NOTIONAL') or filters.get('MIN_NOTIONAL') or {}
        min_notional = float(notional.get('minNotional', '0') or 0)

        out[symbol] = {
            'min_notional': min_notional,
            'step_size': step,
            'min_qty': min_qty
        }
    return out
