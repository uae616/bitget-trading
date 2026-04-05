import requests


def send_telegram_message(cfg: dict, text: str, log=None) -> bool:
    token = str(cfg.get("secrets", {}).get("telegram_token", "") or "").strip()
    chat_id = str(cfg.get("secrets", {}).get("telegram_chat_id", "") or "").strip()

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code >= 400:
            if log:
                log.warning(f"Telegram notify failed: {r.status_code} {r.text}")
            return False
        return True
    except Exception as e:
        if log:
            log.warning(f"Telegram notify error: {e}")
        return False
