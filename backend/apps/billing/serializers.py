from rest_framework import serializers
from .models import BlockedSTKNumber, CommissionRecord, HotspotPlan, SalesAgent, Transaction

class HotspotPlanSerializer(serializers.ModelSerializer):
    max_download_kbps = serializers.IntegerField(source='download_speed_kbps', required=False)
    max_upload_kbps = serializers.IntegerField(source='upload_speed_kbps', required=False)
    max_devices = serializers.IntegerField(source='simultaneous_devices', required=False)
    duration_value = serializers.IntegerField(min_value=1, required=False)
    duration_unit = serializers.ChoiceField(
        choices=('minutes', 'hours', 'days'),
        required=False,
    )

    class Meta:
        model = HotspotPlan
        fields = [
            'id', 'tenant', 'name', 'price', 'duration_minutes',
            'duration_value', 'duration_unit',
            'currency',
            'download_speed_kbps', 'upload_speed_kbps', 'simultaneous_devices',
            'max_download_kbps', 'max_upload_kbps', 'max_devices',
            'is_active', 'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        if (
            'duration_value' not in attrs
            and 'duration_unit' not in attrs
            and 'duration_minutes' in attrs
        ):
            attrs['duration_value'] = attrs['duration_minutes']
            attrs['duration_unit'] = 'minutes'
        else:
            attrs.setdefault(
                'duration_value',
                getattr(self.instance, 'duration_value', 60),
            )
            attrs.setdefault(
                'duration_unit',
                getattr(self.instance, 'duration_unit', 'minutes'),
            )

        unit_minutes = {'minutes': 1, 'hours': 60, 'days': 1440}
        attrs['duration_minutes'] = attrs['duration_value'] * unit_minutes[attrs['duration_unit']]
        if attrs['duration_minutes'] <= 0:
            raise serializers.ValidationError({'duration_value': 'Duration must be positive.'})
        return attrs

class TransactionSerializer(serializers.ModelSerializer):
    payment_ref = serializers.CharField(source='checkout_request_id', read_only=True)
    customer_phone = serializers.CharField(source='phone_number', read_only=True)
    customer_mac = serializers.CharField(source='client_mac', read_only=True)
    nas_id = serializers.PrimaryKeyRelatedField(source='nas', read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(source='plan', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'tenant', 'nas_id', 'plan_id', 'payment_ref',
            'customer_phone', 'customer_mac', 'gross_amount', 'platform_fee',
            'vendor_net_amount', 'gateway_fee', 'gateway_receipt', 'paid_at',
            'payment_method', 'status', 'created_at', 'updated_at',
            'checkout_request_id',
        ]


class TransactionStatusSerializer(serializers.ModelSerializer):
    hotspot_username = serializers.SerializerMethodField()
    hotspot_password = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'checkout_request_id', 'status', 'updated_at',
            'hotspot_username', 'hotspot_password',
        ]

    def get_hotspot_username(self, obj):
        if obj.status != 'COMPLETED':
            return None
        return (obj.phone_number or obj.client_mac or '').strip()

    def get_hotspot_password(self, obj):
        if obj.status != 'COMPLETED':
            return None
        return (obj.phone_number or obj.client_mac or '').strip()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.status != 'COMPLETED':
            data.pop('hotspot_username')
            data.pop('hotspot_password')
        return data


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
