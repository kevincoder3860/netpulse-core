from rest_framework import serializers
from .models import Recharge, Voucher


class VoucherSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    class Meta:
        model = Voucher
        fields = '__all__'


class RechargeSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    router_name = serializers.CharField(source='router.shortname', read_only=True)
    class Meta:
        model = Recharge
        fields = '__all__'
        read_only_fields = ['status', 'plan_name', 'router_name']
