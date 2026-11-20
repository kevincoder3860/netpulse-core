from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from apps.vouchers.models import Recharge
from apps.tenants.models import Tenant
from apps.radius.models import RadCheck
from .models import Customer, Invoice, PlatformSettings, PlatformUser, SupportTicket, TicketMessage


class TenantOwnedSerializer(serializers.ModelSerializer):
    tenant_id = serializers.PrimaryKeyRelatedField(source='tenant', queryset=Tenant.objects.all())

    def validate_tenant_id(self, tenant):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and not user.is_superadmin:
            from core.permissions import tenant_for_user
            if tenant != tenant_for_user(user):
                raise serializers.ValidationError('Tenant does not belong to the authenticated account.')
        return tenant


class CustomerSerializer(TenantOwnedSerializer):
    portal_password = serializers.CharField(write_only=True, min_length=8, required=False, allow_blank=True)
    pppoe_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'tenant_id', 'username', 'name', 'phone_number', 'mac_address',
            'service_type', 'plan_name', 'pppoe_password', 'status', 'ip_address', 'uptime_seconds',
            'download_bytes', 'upload_bytes', 'expires_at', 'created_at', 'portal_password',
        ]
        read_only_fields = ['id', 'created_at', 'uptime_seconds', 'download_bytes', 'upload_bytes']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        current_status = str(instance.status).lower()
        if current_status == Customer.Status.BLOCKED:
            return data

        now = timezone.now()
        if current_status == 'pending':
            active_recharge = Recharge.objects.filter(
                tenant_id=instance.tenant_id,
                username=instance.username,
                expires_at__gt=now,
            ).order_by('-expires_at').first()
            if active_recharge:
                data['status'] = Customer.Status.ACTIVE.value
                data['expires_at'] = active_recharge.expires_at
            elif instance.expires_at and instance.expires_at <= now:
                data['status'] = Customer.Status.EXPIRED.value
        elif instance.expires_at and instance.expires_at <= now:
            data['status'] = Customer.Status.EXPIRED.value
        return data

    def validate_portal_password(self, value):
        if value:
            validate_password(value)
        return value

    def validate(self, attrs):
        service_type = attrs.get('service_type', getattr(self.instance, 'service_type', None))
        if service_type == Customer.ServiceType.PPPOE and not attrs.get('pppoe_password') and not self.instance:
            raise serializers.ValidationError({'pppoe_password': 'A PPPoE password is required.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('portal_password', '')
        pppoe_password = validated_data.pop('pppoe_password', '')
        customer = super().create(validated_data)
        if password:
            User = get_user_model()
            if User.objects.filter(username=customer.username).exists():
                raise serializers.ValidationError({'username': 'An account with this username already exists.'})
            user = User.objects.create_user(username=customer.username, password=password)
            customer.user = user
            customer.save(update_fields=['user'])
        if pppoe_password:
            RadCheck.objects.using('radius_db').update_or_create(
                username=customer.username,
                attribute='Cleartext-Password',
                defaults={'op': ':=', 'value': pppoe_password},
            )
        return customer

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop('portal_password', '')
        pppoe_password = validated_data.pop('pppoe_password', '')
        customer = super().update(instance, validated_data)
        if password:
            if not customer.user:
                User = get_user_model()
                if User.objects.filter(username=customer.username).exists():
                    raise serializers.ValidationError({'username': 'An account with this username already exists.'})
                customer.user = User.objects.create_user(username=customer.username, password=password)
                customer.save(update_fields=['user'])
            else:
                customer.user.set_password(password)
                customer.user.save(update_fields=['password'])
        if pppoe_password:
            RadCheck.objects.using('radius_db').update_or_create(
                username=customer.username,
                attribute='Cleartext-Password',
                defaults={'op': ':=', 'value': pppoe_password},
            )
        return customer


class InvoiceSerializer(TenantOwnedSerializer):
    class Meta:
        model = Invoice
        fields = [
            'id', 'tenant_id', 'invoice_number', 'customer_name', 'customer_phone',
            'plan_name', 'amount', 'date', 'due_date', 'status', 'payment_ref', 'created_at',
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at']

    def create(self, validated_data):
        tenant = validated_data['tenant']
        last_number = Invoice.objects.filter(tenant=tenant).count() + 1
        validated_data['invoice_number'] = f'{tenant.id.hex[:6].upper()}-{last_number:06d}'
        return super().create(validated_data)


class TicketMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMessage
        fields = ['id', 'sender', 'is_staff', 'text', 'created_at']
        read_only_fields = ['id', 'sender', 'is_staff', 'created_at']


class SupportTicketSerializer(TenantOwnedSerializer):
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'tenant_id', 'ticket_number', 'customer_name', 'customer_phone',
            'subject', 'description', 'priority', 'status', 'created_at', 'updated_at', 'messages',
        ]
        read_only_fields = ['id', 'ticket_number', 'created_at', 'updated_at', 'messages']

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        customer = getattr(getattr(request, 'user', None), 'customer_profile', None)
        if customer:
            validated_data.update({
                'tenant': customer.tenant,
                'customer_name': customer.name,
                'customer_phone': customer.phone_number,
            })
        ticket = super().create(validated_data)
        TicketMessage.objects.create(
            ticket=ticket,
            sender=ticket.customer_name,
            is_staff=False,
            text=ticket.description,
        )
        return ticket


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = [
            'platform_name', 'currency', 'default_commission_pct', 'mpesa_paybill',
            'mpesa_env', 'radius_auth_port', 'radius_acct_port', 'session_timeout_secs',
            'support_email', 'maintenance_mode',
        ]


class PlatformUserSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user_id', read_only=True)
    username = serializers.CharField(source='user.username')
    email = serializers.EmailField(source='user.email')
    is_active = serializers.BooleanField(source='user.is_active', required=False)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = PlatformUser
        fields = ['id', 'username', 'email', 'role', 'is_active', 'last_login', 'created_at', 'password']
        read_only_fields = ['id', 'last_login', 'created_at']

    def validate_email(self, value):
        User = get_user_model()
        existing = User.objects.filter(email__iexact=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.user_id)
        if existing.exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate(self, attrs):
        if not self.instance and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'A password is required when creating a system user.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user_data = validated_data.pop('user')
        password = validated_data.pop('password')
        User = get_user_model()
        user = User.objects.create_user(
            username=user_data['username'],
            email=user_data['email'],
            password=password,
            is_active=user_data.get('is_active', True),
        )
        is_superadmin = validated_data['role'] == PlatformUser.Role.SUPERADMIN
        user.is_staff = is_superadmin
        user.is_superuser = is_superadmin
        user.save(update_fields=['is_staff', 'is_superuser'])
        platform_user, _ = PlatformUser.objects.update_or_create(
            user=user,
            defaults=validated_data,
        )
        return platform_user

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        password = validated_data.pop('password', None)
        for field, value in user_data.items():
            setattr(instance.user, field, value)
        if password:
            instance.user.set_password(password)
        is_superadmin = validated_data.get('role', instance.role) == PlatformUser.Role.SUPERADMIN
        instance.user.is_staff = is_superadmin
        instance.user.is_superuser = is_superadmin
        instance.user.save()
        return super().update(instance, validated_data)
