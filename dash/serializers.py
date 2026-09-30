from rest_framework import serializers
from .models import Transaction


class ItemSerializer(serializers.Serializer):
    item_id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=200)
    qty = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class TransactionSerializer(serializers.Serializer):
    venue_id = serializers.CharField(max_length=20)
    transaction_id = serializers.CharField(max_length=64)
    timestamp = serializers.DateTimeField()
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    items = ItemSerializer(many=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    staff_id = serializers.CharField(max_length=32)
