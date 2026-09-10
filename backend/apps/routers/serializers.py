import ipaddress

from rest_framework import serializers
from .models import NAS


class NASSerializer(serializers.ModelSerializer):
    ip_address = serializers.CharField(source='nas_ip', required=False)
    api_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    shared_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = NAS
        fields = [
            'id', 'tenant', 'nasname', 'shortname', 'nas_ip', 'ip_address', 'mac_address', 'secret',
            'api_port', 'api_username', 'api_password', 'radius_server_ip', 'shared_secret',
            'type', 'is_online', 'status', 'last_ping', 'last_provisioned_at', 'created_at', 'updated_at'
        ]

    def validate_nas_ip(self, value):
        value = value.strip()
        if value:
            try:
                ipaddress.ip_address(value)
            except ValueError as exc:
                raise serializers.ValidationError('Enter a valid router IP address.') from exc
        return value

    def validate_radius_server_ip(self, value):
        value = value.strip()
        if value:
            try:
                ipaddress.ip_address(value)
            except ValueError as exc:
                raise serializers.ValidationError('Enter a valid RADIUS server IP address.') from exc
        return value

    def validate_api_port(self, value):
        if not 1 <= value <= 65535:
            raise serializers.ValidationError('API port must be between 1 and 65535.')
        return value

    def validate(self, attrs):
        tenant = attrs.get('tenant') or getattr(self.instance, 'tenant', None)
        nasname = attrs.get('nasname')
        if nasname is None and self.instance is not None:
            return attrs
        nasname = (nasname or '').strip()
        if not nasname:
            raise serializers.ValidationError({'nasname': 'Router name or IP is required.'})
        attrs['nasname'] = nasname
        return attrs

    def create(self, validated_data):
        api_password = validated_data.pop('api_password', '')
        shared_secret = validated_data.pop('shared_secret', '')

        if api_password:
            validated_data['api_password'] = api_password
        else:
            validated_data['api_password'] = validated_data.get('api_password', '')

        if shared_secret:
            validated_data['shared_secret'] = shared_secret
        else:
            validated_data['shared_secret'] = validated_data.get('secret', '')

        nasname = validated_data['nasname']
        router, _ = NAS.objects.update_or_create(
            nasname=nasname,
            defaults=validated_data,
        )
        return router

    def update(self, instance, validated_data):
        api_password = validated_data.pop('api_password', None)
        shared_secret = validated_data.pop('shared_secret', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if api_password:
            instance.api_password = api_password
        if shared_secret:
            instance.shared_secret = shared_secret
            instance.secret = shared_secret
        instance.save()
        return instance
