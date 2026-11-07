from decimal import Decimal


def invoice_total(unit_price: str, quantity: int) -> Decimal:
    if quantity < 0:
        raise ValueError("quantity must be nonnegative")
    return (Decimal(unit_price) * quantity).quantize(Decimal("0.01"))
