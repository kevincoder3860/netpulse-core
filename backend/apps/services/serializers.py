from rest_framework import serializers
from .models import BurstProfile, FUPProfile


class BurstProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BurstProfile
        fields = '__all__'


class FUPProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FUPProfile
        fields = '__all__'
