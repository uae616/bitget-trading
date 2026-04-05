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

# Find HYPER's exact position
for i, (base, vol) in enumerate(candidates):
    if base == 'HYPER':
        print(f'HYPER rank: #{i+1} with volume {vol:,.0f}')
        print(f'HYPER is beyond top-18 cutoff')
        print(f'If top-20 was used, HYPER would rank #{i+1} (still excluded)')
        break
