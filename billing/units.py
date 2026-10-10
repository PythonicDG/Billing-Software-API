from decimal import Decimal
from rest_framework import serializers


def pieces_per_unit(product, unit):
    if unit == 'PIECE':
        return 1
    if unit == 'CENT':
        return 10
    if unit == 'CASE' and product:
        pieces = product.cent_in_per_cs * Decimal('10')
        if pieces > 0 and pieces == pieces.to_integral_value():
            return int(pieces)
        raise serializers.ValidationError(
            {'unit': 'Case requires cents per case representing a positive whole number of units.'}
        )
    raise serializers.ValidationError({'unit': 'Invalid billing unit.'})
