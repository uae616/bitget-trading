def maybe_reconcile(cfg: dict, state: dict, log, spot_api=None):
    # In DRY_RUN paper trading, do NOT overwrite simulated state with real balances
    if bool(cfg["bot"].get("dry_run", True)):
        return

    every = int(cfg["bot"].get("reconcile_every_cycles", 0))
    cycle = int(state.get("meta", {}).get("cycle", 0))
    if every <= 0 or cycle % every != 0:
        return

    if not spot_api:
        log.info("Reconcile skipped (no spot_api).")
        return

    try:
        acct = spot_api.account()
        balances = {b["asset"]: float(b["free"]) for b in acct.get("balances", [])}
        usdt = balances.get(cfg["portfolio"]["quote_asset"], None)
        if usdt is not None:
            state["cash_usdt"] = float(usdt)
        log.info("Reconcile done (cash updated from account free balance).")
    except Exception as e:
        log.warning(f"Reconcile failed: {e}")
