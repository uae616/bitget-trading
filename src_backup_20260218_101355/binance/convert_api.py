import time

class ConvertAPI:
    def __init__(self, client):
        self.client = client

    def get_quote(self, from_asset: str, to_asset: str, from_amount=None, to_amount=None, walletType='SPOT', validTime='10s'):
        params = {
            'fromAsset': from_asset,
            'toAsset': to_asset,
            'fromAmount': from_amount,
            'toAmount': to_amount,
            'walletType': walletType,
            'validTime': validTime
        }
        return self.client.signed_post('/sapi/v1/convert/getQuote', params)

    def accept_quote(self, quote_id: str):
        return self.client.signed_post('/sapi/v1/convert/acceptQuote', {'quoteId': quote_id})

    def order_status(self, order_id=None, quote_id=None):
        return self.client.signed_get('/sapi/v1/convert/orderStatus', {'orderId': order_id, 'quoteId': quote_id})

    def convert_sell_to_usdt(self, coin: str, qty: float, timeout=5.0):
        quote = self.get_quote(from_asset=coin, to_asset='USDT', from_amount=qty)
        quote_id = quote.get('quoteId')
        if not quote_id:
            return None

        accept = self.accept_quote(quote_id)
        order_id = accept.get('orderId')
        if not order_id:
            return None

        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.order_status(order_id=order_id)
            if st and st.get('orderStatus') in ('SUCCESS', 'FAIL'):
                return st
            time.sleep(0.25)
        return None
