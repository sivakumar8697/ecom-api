import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import status, serializers
from rest_framework.generics import RetrieveUpdateAPIView, CreateAPIView, ListCreateAPIView, ListAPIView, \
    RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from .cron import referral_report_cron
from .models import Payout, RewardClaim, Order, BankDetail, KYCImage
from .reports import dashboard_statistics, custom_payout_report, team_details_report, primary_reward_criteria_status, \
    referral_report, team_details_tree_report
from .serializers import UserSerializer, OrderSerializer, PrimaryRewardPointSerializer, PRPMatchingSerializer, \
    SecondaryRewardPointSerializer, PayoutSerializer, BankDetailSerializer, KYCImageSerializer, \
    SpotRewardPointSerializer
from .utils import generate_otp, gen_auth_token, hash_otp, reward_allocation, send_otp_sms

User = get_user_model()


class GenerateOTPAPIView(APIView):
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        user, created = User.objects.get_or_create(mobile_number=mobile_number)
        otp, hashed_otp = generate_otp()
        print(otp)
        auth_hash = gen_auth_token()
        validity = timezone.now() + datetime.timedelta(minutes=5)
        user.otp = hashed_otp
        user.hash = auth_hash
        user.validity = validity
        user.save()
        response = {
            'message': 'OTP sent successfully.',
            'mobile': mobile_number,
            'hash': auth_hash
        }
        # Remove the country code from the mobile number
        if mobile_number.startswith("+"):
            mobile_number = mobile_number[3:]
        send_otp_sms(mobile_number, otp)
        return Response(response)


class VerifyOTPAPIView(APIView):
    def post(self, request):
        otp = request.data.get('otp')
        hashed_otp = hash_otp(otp)
        otp_hash = request.data.get('hash')
        mobile_number = request.data.get('mobile_number')
        try:
            user = User.objects.get(mobile_number=mobile_number, otp=hashed_otp, hash=otp_hash)
        except User.DoesNotExist:
            return Response({'error': 'Invalid mobile number or OTP'}, status=400)
        else:
            # OTP is valid, authenticate the user and generate tokens
            if not user.validity >= timezone.now():
                return Response({'error': 'OTP expired'}, status=400)
            access_token = AccessToken.for_user(user)
            refresh_token = RefreshToken.for_user(user)

            user.otp = None  # Clear the OTP after successful authentication
            user.is_verified = True
            user.save()

            return Response({'access_token': str(access_token), 'refresh_token': str(refresh_token)})


class RefreshTokenAPIView(APIView):
    def post(self, request):
        refresh_token = request.data.get('refresh_token')

        try:
            refresh_token = RefreshToken(refresh_token)
            access_token = refresh_token.access_token
        except Exception as e:
            return Response({'error': 'Invalid refresh token'}, status=400)

        return Response({'access_token': str(access_token)})


class UserDetailsAPIView(RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        extra_data = {}
        partial = kwargs.pop('partial', False)
        instance = request.user
        if 'referral_id' in request.data.keys():
            referred_user = User.objects.filter(mobile_number__contains=request.data['referral_id']).first()
            extra_data['referred_user'] = referred_user.pk
            # Create a SpotRewardPoint instance
            spot_reward_data = {
                'eligible_user': referred_user.pk,
                'referral': instance.pk
            }
            spot_reward_serializer = SpotRewardPointSerializer(data=spot_reward_data)
            if spot_reward_serializer.is_valid():
                spot_reward_serializer.save()
        serializer = self.get_serializer(instance, data=request.data, partial=partial, context=extra_data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance = self.get_object()
        # if 'referral_id' in serializer.validated_data.keys():  # and 'is_free' not in serializer.validated_data.keys()
        #     reward_allocation_ = reward_allocation(instance, referred_user)ch
        #     prp_serializer = PrimaryRewardPointSerializer(data=reward_allocation_)
        #     prp_serializer.is_valid(raise_exception=True)
        #     prp_serializer.save()
        #     if reward_allocation_['matching_user2'] is not None:
        #         reward_allocation_['PRP_id'] = prp_serializer.instance.pk
        #         prp_matching = PRPMatchingSerializer(data=reward_allocation_)
        #         prp_matching.is_valid(raise_exception=True)
        #         prp_matching.save()
        #         if reward_allocation_['secondary_match']:
        #             srp_matching = SecondaryRewardPointSerializer(data=reward_allocation_)
        #             srp_matching.is_valid(raise_exception=True)
        #             srp_matching.save()

        return Response(serializer.data)


class CreateOrderView(CreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, request, *args, **kwargs):
        data = request.data
        # Calculate new price and tax values for each item      # To be commented out in next release
        order_items = data['order_items']
        for item in order_items:
            item['price'] = 2208.00
            item['tax'] = 125.00

        # Calculate new total_amount and total_tax
        total_amount = sum(item['price'] for item in order_items)
        total_tax = sum(item['tax'] for item in order_items)

        # Update the request data with the new total_amount and total_tax
        data['total_amount'] = Decimal(total_amount)
        data['total_tax'] = Decimal(total_tax)
        # --- end ---
        user = data['user']
        order_status = request.initial_data['order_complete']
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        headers = self.get_success_headers(serializer.validated_data)

        if 'referral_id' in user.keys() and user.get('referral_id') is not None and order_status:
            referred_user = User.objects.filter(mobile_number__contains=user.get('referral_id')).first()
            reward_allocation_ = reward_allocation(User.objects.get(pk=user.get('id')), referred_user)
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

        return Response(serializer.validated_data, status=status.HTTP_201_CREATED, headers=headers)


class OrderList(ListAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        user = self.request.user
        return Order.objects.filter(user=user.pk)


class OrderDetail(RetrieveAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        user = self.request.user
        return Order.objects.filter(user=user.pk)


class CreatePayoutView(ListCreateAPIView):
    serializer_class = PayoutSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Payout.objects.filter(user=user)

    def perform_create(self, request, *args, **kwargs):
        data = request.data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        headers = self.get_success_headers(serializer.validated_data)
        return Response(serializer.validated_data, status=status.HTTP_201_CREATED, headers=headers)


class PayoutReportView(APIView):

    def generate_user_report(self, user, start_date, end_date):
        report_data = custom_payout_report(user, start_date, end_date)
        user_data = {
            "Name": user.full_name,
            "MobileNo": user.mobile_number.national_number,
            "userId": str(user.pk),
            **report_data  # Include the report data for the user
        }
        return user_data

    def post(self, request):
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        data = {
            "start_date": start_date,
            "end_date": end_date,
            "reportData": []
        }

        if not isinstance(request.user, AnonymousUser):
            user = request.user
            user_data = self.generate_user_report(user, start_date, end_date)
            data["reportData"].append(user_data)
        else:
            users = User.objects.all()
            for user in users:
                user_data = self.generate_user_report(user, start_date, end_date)
                data["reportData"].append(user_data)

        return Response(data)


class RewardReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        report = primary_reward_criteria_status(user)
        return Response(report)

    def post(self, request):
        data = request.data
        report = RewardClaim.objects.update_or_create(user=request.user,
                                                      status=data['status'],
                                                      claimed_on=data['claimed_on'],
                                                      criteria=data['criteria'])

        return Response(data, status=status.HTTP_201_CREATED)


class DashboardView(APIView):

    def get(self, request):
        user = None
        if request.user.is_authenticated:
            user = request.user
        data = dashboard_statistics(user)

        return Response(data)


class ReferralReportView(APIView):

    def get(self, request):
        user = None
        if request.user.is_authenticated:
            user = request.user
        data = referral_report(user)

        return Response(data)


class TeamDetailsView(APIView):
    def post(self, request):
        current_user = request.user
        team_details = team_details_report(current_user, request)
        return Response(team_details)


class FetchUserView(APIView):
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        if mobile_number:
            try:
                user = User.objects.get(mobile_number=mobile_number)
                serializer = UserSerializer(user)
                return Response(serializer.data)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=404)
        else:
            return Response({"error": "Mobile number parameter is missing."}, status=400)


class BankDetailListCreateView(ListCreateAPIView):
    serializer_class = BankDetailSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        return BankDetail.objects.filter(user=self.request.user)


class KYCImageView(ListCreateAPIView):
    serializer_class = KYCImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return KYCImage.objects.filter(user=user)

    def perform_create(self, serializer):
        user = self.request.user
        proof_type = self.request.data.get('proof_type')
        if proof_type == 'ID1':
            if KYCImage.objects.filter(user=user, proof_type='ID1').exists():
                raise serializers.ValidationError("Only one 'ID1' proof image allowed.")
        elif proof_type == 'ID2':
            if KYCImage.objects.filter(user=user, proof_type='ID2').count() >= 2:
                raise serializers.ValidationError("Maximum of two 'ID2' proof images allowed.")
        serializer.save(user=user)


class TeamDetailsTreeView(APIView):

    def get(self, request):
        current_user = request.user
        team_details_tree = team_details_tree_report(current_user)
        return Response(team_details_tree)