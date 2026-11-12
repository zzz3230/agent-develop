from decimal import Decimal, ROUND_HALF_UP
def to_cents(text):
    return int((Decimal(text)*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))
