from decimal import Decimal, ROUND_DOWN

def floor_to_step(qty: float, step: float) -> float:
    q = Decimal(str(qty))
    s = Decimal(str(step))
    if s == 0:
        return float(q)
    return float((q // s) * s)

def floor_to_precision(qty: float, precision: int) -> float:
    q = Decimal(str(qty))
    quant = Decimal('1').scaleb(-precision)  # 10^-precision
    return float(q.quantize(quant, rounding=ROUND_DOWN))
