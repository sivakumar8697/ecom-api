from api.models import User
from api.reports import payout_report, referral_report


def payout_report_cron():
    user = User.objects.all()
    for user in user:
        payout_report(user)


def referral_report_cron(user=None):

    # users = User.objects.all()
    # for user in users:
    #     referrals = User.objects.filter(referral_id=user.pk)     # uncomment this when this function moved to cron
    #     for user in referrals:
    #         referral_report(user)

    referrals = User.objects.filter(referral_id=user.pk, order_complete=True)
    for user in referrals:
        referral_report(user)
