def run_mt5_scalper(*args, **kwargs):
	# Lazy import avoids runpy warning when executing `python -m src.mt5_scalper.main`.
	from .main import run_mt5_scalper as _run

	return _run(*args, **kwargs)


__all__ = ["run_mt5_scalper"]
