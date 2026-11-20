from rest_framework import serializers
from .models import Tenant, TenantStaff, TenantUser
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken


class TenantPaystackFieldsSerializer(serializers.ModelSerializer):
    paystack_secret_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    paystack_secret_key_set = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tenant
        fields = ['billing_email', 'paystack_secret_key', 'paystack_secret_key_set']

    def create(self, validated_data):
        secret_key = validated_data.pop('paystack_secret_key', '')
        tenant = super().create(validated_data)
        if secret_key:
            tenant.set_paystack_secret_key(secret_key)
            tenant.save(update_fields=['paystack_secret_key', 'updated_at'])
        return tenant

    def update(self, instance, validated_data):
        secret_key = validated_data.pop('paystack_secret_key', '')
        tenant = super().update(instance, validated_data)
        if secret_key:
            tenant.set_paystack_secret_key(secret_key)
            tenant.save(update_fields=['paystack_secret_key', 'updated_at'])
        return tenant


class TenantSerializer(TenantPaystackFieldsSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'


class TenantBrandingSerializer(TenantPaystackFieldsSerializer):
    class Meta:
        model = Tenant
        fields = [
            'logo_url', 'brand_color', 'welcome_headline', 'terms_of_service',
            'billing_email', 'paystack_secret_key', 'paystack_secret_key_set',
        ]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    business_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20)

    def validate_email(self, value):
        User = get_user_model()
        if User.objects.filter(email__iexact=value).exists() or Tenant.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate(self, attrs):
        company_name = (attrs.get('company_name') or attrs.get('business_name') or '').strip()
        if not company_name:
            raise serializers.ValidationError({'company_name': 'This field is required.'})
        attrs['business_name'] = company_name
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        User = get_user_model()
        email = validated_data['email']
        username = email
        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data['password'],
            first_name=validated_data.get('first_name', '').strip(),
            last_name=validated_data.get('last_name', '').strip(),
        )
        tenant = Tenant.objects.create(
            business_name=validated_data['business_name'],
            email=email,
            phone_number=validated_data['phone_number'],
            status='ACTIVE',
        )
        TenantUser.objects.create(user=user, tenant=tenant, role=TenantUser.Role.VENDOR)
        refresh = RefreshToken.for_user(user)
        return {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': TenantUser.Role.VENDOR,
                'is_vendor': True,
            },
            'tenant': TenantSerializer(tenant).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


class StaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = TenantStaff
        fields = ['id', 'username', 'email', 'role', 'is_active', 'created_at']


class StaffInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=TenantStaff.Role.choices)

    @transaction.atomic
    def create(self, validated_data):
        User = get_user_model()
        email = validated_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({'email': 'A user with this email already exists.'})
        user = User.objects.create_user(username=email, email=email, password=validated_data['password'])
        staff = TenantStaff.objects.create(user=user, tenant=self.context['tenant'], role=validated_data['role'])
        return staff
