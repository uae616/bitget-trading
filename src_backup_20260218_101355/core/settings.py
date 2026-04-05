import os
from dotenv import load_dotenv

def load_config() -> dict:
    load_dotenv()
    try:
        import tomllib  # py>=3.11
    except Exception:
        import tomli as tomllib

    with open('config.toml', 'rb') as f:
        cfg = tomllib.load(f)

    cfg['secrets'] = {
        'api_key': os.getenv('BINANCE_API_KEY', ''),
        'api_secret': os.getenv('BINANCE_API_SECRET', ''),
        'telegram_token': os.getenv('TELEGRAM_TOKEN', ''),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
    }
    return cfg
