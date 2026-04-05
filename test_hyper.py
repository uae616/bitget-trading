import ccxt

exchange = ccxt.binance({'enableRateLimit': True})
exchange.load_markets()

_STABLE_BASES = {
    'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FDUSD', 'USDE', 'USD1', 'PYUSD'
}

tickers = exchange.fetch_tickers()
candidates = []
for sym, t in tickers.items():
    if not sym.endswith('/USDT'):
        continue
    vol = t.get('quoteVolume') or 0
    base = sym.split('/')[0]
    candidates.append((base, vol))

candidates.sort(key=lambda x: x[1], reverse=True)

# Show all candidates with rank, highlighting HYPER and top cutoffs
print('CANDIDATES RANKED BY VOLUME:')
print('Rank  Symbol        Volume              Stable')
print('-' * 60)
for i, (base, vol) in enumerate(candidates[:30], 1):
    is_stable = base.upper() in _STABLE_BASES
    marker = ''
    if i == 18:
        marker = ' <-- TOP 18 CUTOFF'
    elif i == 20:
        marker = ' <-- TOP 20 CUTOFF'
    elif base == 'HYPER':
        marker = ' <-- HYPERUSDT'
    vol_str = f'{vol:,.0f}'
    print(f'{i:3}   {base:12} {vol_str:>18}  {str(is_stable):5}{marker}')

# Filter like main.py does
top_18_filtered = [c[0] for c in candidates[:18] if c[0].upper() not in _STABLE_BASES]
print(f'\n\nTOP 18 RESULT (after stable filtering):')
print(', '.join(top_18_filtered))
print(f'Count: {len(top_18_filtered)} symbols')
