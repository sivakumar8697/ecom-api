from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import User, OrderItem, Address, Order, PrimaryRewardPoint, PRPMatching, SecondaryRewardPoint, Payout, \
    BankDetail, KYCImage, SpotRewardPoint
from .utils import reward_allocation

User = get_user_model()


def reward_matching(user):
    # Reward logic
    referred_user = User.objects.filter(pk=user.referral_id).first()
    reward_allocation_ = reward_allocation(User.objects.get(pk=user.pk), referred_user)
    prp_serializer = PrimaryRewardPointSerializer(data=reward_allocation_)
    prp_serializer.is_valid(raise_exception=True)
    prp_serializer.save()
    if reward_allocation_['matching_user2'] is not None:
        reward_allocation_['PRP_id'] = prp_serializer.instance.pk
        prp_matching = PRPMatchingSerializer(data=reward_allocation_)
        prp_matching.is_valid(raise_exception=True)
        prp_matching.save()
        if reward_allocation_['secondary_match'] is not None:
            srp_matching = SecondaryRewardPointSerializer(data=reward_allocation_)
            srp_matching.is_valid(raise_exception=True)
            srp_matching.save()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'full_name', 'email', 'birth_date', 'gender', 'mobile_number', 'referral_id', 'pan', 'is_updated',
            'is_admin', 'is_free')

    def create(self, validated_data):
        user = User(**validated_data)
        user.save()
        return user

    def update(self, instance, validated_data):
        if "referred_user" in self.context.keys():
            instance.referral_id = self.context['referred_user']
        if 'is_free' in validated_data.keys():
            instance.is_free = True if validated_data['is_free'] else False
        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.email = validated_data.get('email', instance.email)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.gender = validated_data.get('gender', instance.gender)
        instance.pan = validated_data.get('pan', instance.pan)
        instance.is_updated = True
        instance.save()
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.referral_id:
            serializer = User.objects.get(pk=instance.referral_id)
            representation['referral_id'] = serializer.mobile_number.national_number
        return representation


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['description', 'price', 'tax', 'quantity', 'size']


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['address_line1', 'address_line2', 'landmark', 'city', 'pincode']


class PrimaryRewardPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrimaryRewardPoint
        fields = ['date', 'PRP_user', 'referred_by', 'new_user', 'matching_count']

    def create(self, validated_data):
        prp = PrimaryRewardPoint(**validated_data)
        prp.save()
        return prp


class PRPMatchingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PRPMatching
        fields = ['PRP_id', 'matching_user1', 'matching_user2']

    def create(self, validated_data):
        prp_match = PRPMatching(**validated_data)
        prp_match.save()
        return prp_match


class SecondaryRewardPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecondaryRewardPoint
        fields = ['PRP_id', 'referred_su1', 'referred_su2', 'eligible_su', 'reward_category']

    def create(self, validated_data):
        srp_match = SecondaryRewardPoint(**validated_data)
        srp_match.save()
        return srp_match


class SpotRewardPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpotRewardPoint
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True)
    shipping_address = AddressSerializer()
    user = UserSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ('order_id', 'invoice_number', 'total_amount', "total_tax", "shipping_address", 'order_items', 'user',
                  'delivered_on', 'delivery_partner', 'payment_status', 'payment_method')

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        user.order_complete = True
        user.is_free = False
        user.save()
        order_items_data = validated_data.pop('order_items')
        address_data = validated_data.pop('shipping_address')
        shipping_address, _ = Address.objects.get_or_create(user=user, **address_data)
        order = Order.objects.create(user=user, shipping_address=shipping_address, **validated_data)
        order_items = [OrderItem(order=order, **item_data) for item_data in order_items_data]
        OrderItem.objects.bulk_create(order_items)

        return order

    def update(self, instance, validated_data):
        payment_status = validated_data.get('payment_status', instance.payment_status)
        instance.payment_status = payment_status
        instance.delivered_on = validated_data.get('delivered_on', instance.delivered_on)
        instance.delivery_partner = validated_data.get('delivery_partner', instance.delivery_partner)
        instance.payment_method = validated_data.get('payment_method', instance.payment_method)
        instance.save()
        if instance.payment_status and instance.payment_status == 'completed':
            if instance.user.referral_id is not None:
                reward_matching(instance.user)

        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        if isinstance(instance, Order) and 'request' in self.context:
            serializer = UserSerializer(self.context['request'].user)
            representation['user'] = serializer.data
            # Add the updated total_amount and total_tax to the representation      #to be commented out in next release
            representation['total_amount'] = instance.total_amount
            representation['total_tax'] = instance.total_tax

        return representation


class PayoutSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = ('user', 'primary_rp', 'secondary_rp', 'spot_rp')

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        payout = Payout(**validated_data)
        payout.user = user
        payout.save()
        return payout

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        primary_rp = instance.get('primary_rp')
        secondary_rp = instance.get('secondary_rp')
        spot_rp = instance.get('spot_rp')

        values = [value for value in [primary_rp, secondary_rp, spot_rp] if value is not None]
        gross = sum(values) if values else None

        representation['gross'] = gross
        representation['tds'] = representation['gross'] * Decimal('0.0327')
        representation['rental'] = representation['gross'] * Decimal('0.0673')
        representation['net'] = representation['gross'] - (representation['tds'] + representation['rental'])
        representation['repurchase'] = representation['net'] * Decimal('0.10')
        representation['final'] = representation['net'] - representation['repurchase']
        return representation


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = '__all__'


class BankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankDetail
        fields = ('account_holder_name', 'account_no', 'ifsc_code', 'account_type', 'branch')

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        banks = BankDetail(**validated_data)
        banks.user = user
        banks.save()
        return banks


class KYCImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCImage
        fields = ('image', 'proof_type')

    def validate(self, data):
        proof_type = data.get('proof_type')
        images = self.context['request'].FILES.getlist('image')

        if proof_type == 'ID1' and len(images) != 1:
            raise serializers.ValidationError("You must provide exactly one image for ID1 proof type.")

        if proof_type == 'ID2' and len(images) != 2:
            raise serializers.ValidationError("You must provide exactly two images for ID2 proof type.")

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        proof_type = validated_data['proof_type']
        images = request.FILES.getlist('image')

        if proof_type == 'ID1':
            if KYCImage.objects.filter(user=user, proof_type='ID1').exists():
                raise serializers.ValidationError("Only one 'ID1' proof image allowed.")
        elif proof_type == 'ID2':
            if KYCImage.objects.filter(user=user, proof_type='ID2').count() >= 2:
                raise serializers.ValidationError("Maximum of two 'ID2' proof images allowed.")

        kyc_images = []
        for image in images:
            kyc = KYCImage(user=user, image=image, proof_type=proof_type)
            kyc.save()
            kyc_images.append(kyc)

        return kyc_images
