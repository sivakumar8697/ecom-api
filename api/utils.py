import hashlib
import random
import uuid
from datetime import datetime, timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.db.models import F
from django.db.models import Q
from django.utils import timezone
from twilio.rest import Client

from api import models

fernet_key = Fernet.generate_key()
url_safe_key = fernet_key.decode('utf-8')
SECRET_KEY = url_safe_key.encode('utf-8')
fernet = Fernet(SECRET_KEY)


def generate_user_id(date_joined, mobile_number):
    user_count = models.User.objects.count()
    mobile_number_ = mobile_number.national_number
    sequence_number = user_count + 1

    user_id = f"{mobile_number_}_{sequence_number}"

    return user_id


def hash_otp(otp):
    otp_byte = str(otp).encode('utf-8')
    return hashlib.sha256(otp_byte).hexdigest()


def generate_otp():
    otp = random.randint(1000, 9999)
    return str(otp), hash_otp(otp)


def send_otp_sms(mobile_number, otp):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=f'Your OTP is: {otp}',
        from_=settings.TWILIO_PHONE_NUMBER,
        to=mobile_number
    )
    return message.sid


def gen_auth_token():
    random = str(uuid.uuid4())
    convert = str(random + "," + settings.SECRET_KEY).encode('utf-8')
    return hashlib.sha256(convert).hexdigest()


# def encrypt_order_id(order_id):
#     encrypted_order_id = fernet.encrypt(str(order_id).encode())
#     return encrypted_order_id
#
#
# def decrypt_order_id(encrypted_order_id):
#     decrypted_order_id_bytes = fernet.decrypt(encrypted_order_id)
#     decrypted_order_id = decrypted_order_id_bytes.decode()
#     return int(decrypted_order_id)


def reward_allocation(new_user, referred_user):
    data = {'matching_count': 0,
            'matching_user2': None,
            'secondary_match': None}

    # finding primary user
    primary_user = models.User.objects.get(pk=referred_user.referral_id) if referred_user.referral_id else referred_user
    matching_user_1 = new_user

    prp_users = models.PrimaryRewardPoint.objects.all()
    prp_users_count = prp_users.count()

    # if PRP table has more than 2 records, exclude the first and last always or else just excluding the first record
    if prp_users_count > 2:
        first_prp_user = prp_users.first()
        last_prp_user = prp_users.last()
        prp_users = prp_users.exclude(Q(matching_count=1) & Q(pk__in=[first_prp_user.pk, last_prp_user.pk]))
    elif prp_users_count == 2:
        first_prp_user = prp_users.first()
        prp_users = prp_users.exclude(Q(matching_count=1) & Q(pk=first_prp_user.pk))

    # matching new user with primary user's direct referral, or it's down-line
    available_for_match = prp_users.filter(PRP_user=primary_user.pk,
                                           matching_count__lt=2)

    if str(referred_user.pk) in available_for_match.values_list('referred_by', flat=True):
        matching_user_2 = available_for_match.get(referred_by=referred_user.pk)
        # It's a parent match, and the matched_user_2 is the first record matching this condition
    else:
        matching_user_2 = available_for_match.first()
        # It's a child match, and the matched_user_2 is the first record matching this condition

    if matching_user_2 is not None:
        matching_user_2.matching_count = F('matching_count') + 1
        matching_user_2.save()
        data['matching_user2'] = matching_user_2.new_user
        data['matching_count'] = 1

        # if both matched user's referred user is different, consider them for secondary reward point
        if matching_user_2.referred_by != str(referred_user.pk):
            data['referred_su1'] = referred_user.pk
            data['referred_su2'] = matching_user_2.referred_by

            selected_user = min([referred_user, models.User.objects.get(pk=matching_user_2.referred_by)],
                                key=lambda user: user.date_joined)  # select the user who joined first

            eligible_su = referred_user if models.SecondaryRewardPoint.objects.filter(
                eligible_su=selected_user).exists() else selected_user  # find the eligible user

            data['eligible_su'] = eligible_su.pk
            data['reward_category'] = 'first_join' if eligible_su == selected_user else 'first_reward'
            data['secondary_match'] = True

    data['PRP_user'] = primary_user.pk
    data['referred_by'] = referred_user.pk
    data['new_user'] = matching_user_1.pk
    data['matching_user1'] = matching_user_1.pk

    return data


def get_last_saturday(today=None):
    if today is None:
        today = timezone.now().date()
    else:
        input_date_str = today
        input_date = datetime.strptime(input_date_str, '%Y-%m-%d')
        today = timezone.make_aware(input_date, timezone.get_current_timezone())

    days_since_saturday = (today.weekday() + 2) % 7
    last_saturday = today - timedelta(days=days_since_saturday)
    last_saturday_datetime = datetime.combine(last_saturday, datetime.min.time())
    last_saturday_aware = timezone.make_aware(last_saturday_datetime, timezone.utc)
    return last_saturday_aware
