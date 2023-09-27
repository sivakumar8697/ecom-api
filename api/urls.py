from django.urls import path

from .views import GenerateOTPAPIView, VerifyOTPAPIView, UserDetailsAPIView, RefreshTokenAPIView, CreateOrderView, \
    CreatePayoutView, PayoutReportView, DashboardView, TeamDetailsView, RewardReportView, FetchUserView, OrderList, \
    OrderDetail, BankDetailListCreateView, KYCImageView, ReferralReportView, TeamDetailsTreeView, OrderUpdateView

urlpatterns = [
    path('otp/generate/', GenerateOTPAPIView.as_view(), name='generate_otp'),
    path('otp/verify/', VerifyOTPAPIView.as_view(), name='verify_otp'),
    path('token/refresh/', RefreshTokenAPIView.as_view(), name='refresh_token'),
    path('user/', UserDetailsAPIView.as_view(), name='user-details'),
    path('create-order/', CreateOrderView.as_view(), name='create_order'),
    path('create-payout/', CreatePayoutView.as_view(), name='create_payout'),
    path('payout-report/', PayoutReportView.as_view(), name='payout_report'),  # to be removed
    path('reward-report/', RewardReportView.as_view(), name='payout_report'),
    path('referral-report/', ReferralReportView.as_view(), name='referral_report'),  # to be removed
    path('dashboard-statistics/', DashboardView.as_view(), name='dashboard_statistics'),
    path('team-details/', TeamDetailsView.as_view(), name='team_details'),
    path('team-details-tree/', TeamDetailsTreeView.as_view(), name='team_details_tree'),
    path('fetch-user/', FetchUserView.as_view(), name='fetch_user'),
    path('orders/', OrderList.as_view(), name='order-list'),
    path('orders/<int:pk>/', OrderDetail.as_view(), name='order-detail'),
    path('orders-update/', OrderUpdateView.as_view(), name='order-update'),
    path('bank-details/', BankDetailListCreateView.as_view(), name='bank-detail-list-create'),
    path('kyc-images/', KYCImageView.as_view(), name='kyc-images')
]
