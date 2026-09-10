from rest_framework import serializers
from .models import BlockedSTKNumber, CommissionRecord, HotspotPlan, SalesAgent, Transaction

class HotspotPlanSerializer(serializers.ModelSerializer):
    max_download_kbps = serializers.IntegerField(source='download_speed_kbps', required=False)
    max_upload_kbps = serializers.IntegerField(source='upload_speed_kbps', required=False)
    max_devices = serializers.IntegerField(source='simultaneous_devices', required=False)

    class Meta:
        model = HotspotPlan
        fields = [
            'id', 'tenant', 'name', 'price', 'duration_minutes',
            'currency',
            'download_speed_kbps', 'upload_speed_kbps', 'simultaneous_devices',
            'max_download_kbps', 'max_upload_kbps', 'max_devices',
            'is_active', 'created_at', 'updated_at',
        ]

class TransactionSerializer(serializers.ModelSerializer):
    payment_ref = serializers.CharField(source='checkout_request_id', read_only=True)
    customer_phone = serializers.CharField(source='phone_number', read_only=True)
    customer_mac = serializers.CharField(source='client_mac', read_only=True)
    nas_id = serializers.PrimaryKeyRelatedField(source='nas', read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(source='plan', read_only=True)

    class Meta:
        model = Transaction
        fields = ['id', 'tenant', 'nas_id', 'plan_id', 'payment_ref', 'customer_phone', 'customer_mac', 'gross_amount', 'platform_fee', 'vendor_net_amount', 'payment_method', 'status', 'created_at', 'updated_at', 'checkout_request_id']


class BlockedSTKNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedSTKNumber
        fields = '__all__'


class SalesAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesAgent
        fields = '__all__'


class CommissionRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRecord
        fields = '__all__'
