# Invoice total specification

`invoice_total(unit_price, quantity)` returns the price multiplied by quantity, rounded to two decimal places.
Quantity must be a nonnegative integer. A negative quantity must raise `ValueError`.
Existing behavior for zero and positive quantities must remain unchanged.
