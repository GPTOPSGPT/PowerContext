from decimal import Decimal


def invoice_total(unit_price: str, quantity: int) -> Decimal:
    return (Decimal(unit_price) * quantity).quantize(Decimal("0.01"))
