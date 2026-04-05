import os
from dotenv import load_dotenv


def _get_first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, '')
        if value:
            return value
    return ''

def load_config() -> dict:
    load_dotenv()
    try:
        import tomllib  # py>=3.11
    except Exception:
        import tomli as tomllib

    with open('config.toml', 'rb') as f:
        cfg = tomllib.load(f)

    # Support both Binance and Bitget credentials
    telegram_token = os.getenv('TELEGRAM_TOKEN', '')
    if not telegram_token:
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')

    cfg['secrets'] = {
        # Binance credentials (legacy)
        'api_key': os.getenv('BINANCE_API_KEY', ''),
        'api_secret': os.getenv('BINANCE_API_SECRET', ''),
        # Bitget credentials
        'bitget_api_key': _get_first_env('BITGET_API_KEY', 'BITGET_API_KET'),
        'bitget_api_secret': os.getenv('BITGET_API_SECRET', ''),
        'bitget_api_passphrase': _get_first_env('BITGET_API_PASSPHRASE', 'BITGET_API_Passphrase'),
        # Telegram
        'telegram_token': telegram_token,
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
        'telegram_enabled': os.getenv('TELEGRAM_ENABLED', 'True').lower() == 'true',
    }
    return cfg
