from collections import defaultdict
from datetime import timedelta, datetime

from django.db import models, connection
from django.db.models import F
from django.db.models.functions import Cast

from api.models import PrimaryRewardPoint, PRPMatching, Configuration, SecondaryRewardPoint, Payout, User, RewardClaim, \
    Order, SpotRewardPoint
from api.utils import get_last_saturday


def matching_report(user):
    prp_ids = PrimaryRewardPoint.objects.filter(PRP_user=user.pk).values_list('pk', flat=True)
    matching_records = PRPMatching.objects.filter(PRP_id__in=prp_ids)

    eligible_teams = matching_records.count()
    total_rewards = eligible_teams * 2000

    report_data = {
        'eligible_teams': eligible_teams,
        'total_rewards': total_rewards,
    }

    return report_data


# Reward Point configurations
table_exists = 'api_configuration' in connection.introspection.table_names()

if table_exists:
    config = Configuration.objects.values('config_name', 'value').all()

    if config is not None:
        config_dict = {data['config_name']: data['value'] for data in config}

        prp = int(config_dict.get('PRP', 0))
        srp = int(config_dict.get('SRP', 0))
        irp = int(config_dict.get('IRP', 0))

        # Dynamically fetch and assign values for RPC1, RPC2, RPC3, etc.
        rpc_values = {key: int(value) for key, value in config_dict.items() if key.startswith('RPC')}
        for i in range(1, len(rpc_values) + 1):
            globals()[f'RPC{i}'] = rpc_values.get(f'RPC{i}', 0)


# <----.----->

def payout_report(user=None, start_date=None, end_date=None, is_org=False):
    start_date = get_last_saturday(start_date)
    if end_date is None:
        end_date = start_date + timedelta(days=6, hours=23, minutes=59)

        if not Payout.objects.filter(start_date=start_date, end_date=end_date, user=user).exists():
            primary_rp = PrimaryRewardPoint.objects.filter(date__range=(start_date, end_date))
            secondary_rp = SecondaryRewardPoint.objects.filter(eligible_su=user.pk)

            primary_reward_total = primary_rp.filter(PRP_user=user.pk).values_list('pk', flat=True)
            primary_reward_count = PRPMatching.objects.filter(PRP_id__in=primary_reward_total).count()
            referral_count = primary_rp.filter(referred_by=user.pk).count()
            primary_reward = primary_reward_count * prp
            secondary_reward = secondary_rp.count() * srp
            spot_reward = SpotRewardPoint.objects.filter(eligible_user=user.pk).count() * irp

            payout = Payout(user=user,
                            start_date=start_date,
                            end_date=end_date,
                            prp_team_count=primary_reward_count,
                            referral_count=referral_count,
                            primary_rp=primary_reward,
                            secondary_rp=secondary_reward,
                            spot_rp=spot_reward)
            payout.save()

            return payout
        else:
            pass
    else:
        payouts = Payout.objects.filter(start_date__date__gte=start_date,
                                        end_date__date__lte=end_date) if is_org else Payout.objects.filter(
            user=user,
            start_date__date__gte=start_date,
            end_date__date__lte=end_date)
        return payouts


def dashboard_statistics(user=None):
    data = {'team_count': 0, }
    prp_data = PrimaryRewardPoint.objects.all()
    users = User.objects.all()
    if user:
        secondary_rp = SecondaryRewardPoint.objects.filter(eligible_su=user.pk)
        data['referral_count'] = User.objects.filter(referral_id=user.pk).count()
        data['spot_reward'] = SpotRewardPoint.objects.filter(eligible_user=user.pk).count() * irp
        if user.referral_id:
            primary_user_down_lines = User.objects.filter(referral_id=user.referral_id)
            primary_user_down_lines_referral_ids = list(primary_user_down_lines.values_list('pk', flat=True))
            primary_user_down_lines_referrals = User.objects.filter(
                referral_id__in=primary_user_down_lines_referral_ids).count()
            # current_user_down_lines = User.objects.filter(referral_id=user.pk)
            # current_user_down_lines_referrals = User.objects.filter(referral_id__in=current_user_down_lines).count()
            # logged-in user is not excluded in the following query
            # data['team_count'] = prp_data.filter((Q(PRP_user=primary_user.PRP_user.pk) if primary_user else Q()) |
            #                                      Q(PRP_user=user.pk) |
            #                                      Q(PRP_user__in=list(primary_user_down_lines)) |
            #                                      Q(referred_by__in=list(primary_user_down_lines))).count()

            data['team_count'] = primary_user_down_lines.count() + primary_user_down_lines_referrals

        # data['self_count'] = current_user_down_lines.count() + current_user_down_lines_referrals

        # if data['team_count'] != data['self_count']:
        #     data['senior_support'] = (data['team_count'] - data['self_count'] if data['team_count'] > data[
        #         'self_count'] else data['self_count'] - data['team_count']) - 1
        # else:
        #     data['senior_support'] = 0
        prp_count = prp_data.filter(PRP_user=user.pk).values_list('pk', flat=True)
        data['primary_reward'] = PRPMatching.objects.filter(PRP_id__in=prp_count).count() * prp
        data['secondary_reward'] = secondary_rp.count() * srp
        data['total_reward'] = data['primary_reward'] + data['secondary_reward'] + data['spot_reward']

        return data

    else:
        data['total_strength'] = users.exclude(is_updated=False).count()
        data['free_users'] = users.filter(is_free=True).count()
        data['order_placed'] = users.filter(order_complete=True).count()
        data['reward_earned'] = 0
        data['non_reward_count'] = 0

        return data


def referral_report(user=None):
    start_date = get_last_saturday()
    end_date = start_date + timedelta(days=6, hours=23, minutes=59)
    referrals = User.objects.filter(referral_id=user.pk)

    user_sales = defaultdict(int)

    for referral in referrals:
        total_sales = PrimaryRewardPoint.objects.filter(date__range=(start_date, end_date),
                                                        referred_by=referral.pk).count()
        user_sales[referral.pk] += total_sales

    report = []
    matched_users = set()

    for referral in referrals:
        user_id = referral.pk
        if user_id in matched_users:
            continue

        total_sales = user_sales[user_id]

        data = {
            'user_id': user_id,
            'name': referral.full_name,
            'mobile_number': referral.mobile_number.national_number,
            'total_sales': total_sales,
            'sales_consider': total_sales,
            'sales_carry_forwarded': 0,
        }

        for other_referral in referrals:
            other_user_id = other_referral.pk
            if user_id != other_user_id and user_sales[other_user_id] > 0:
                carry_forwarded = min(total_sales, user_sales[other_user_id])
                data['sales_consider'] -= carry_forwarded
                data['sales_carry_forwarded'] += carry_forwarded
                matched_users.add(other_user_id)
                user_sales[other_user_id] -= carry_forwarded

        report.append(data)
        matched_users.add(user_id)

    return report


def custom_payout_report(user=None, start_date=None, end_date=None):
    data = {}

    start_date = datetime.strptime(start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)

    end_date = end_date + timedelta(days=1) - timedelta(microseconds=1)

    if user is not None:
        primary_rp = PrimaryRewardPoint.objects.filter(date__range=(start_date, end_date))
        secondary_rp = SecondaryRewardPoint.objects.filter(date__range=(start_date, end_date))

        primary_reward_total = primary_rp.filter(PRP_user=user.pk).values_list('pk', flat=True)
        primary_reward_count = PRPMatching.objects.filter(PRP_id__in=primary_reward_total).count()
        referral_count = primary_rp.filter(referred_by=user.pk).count()
        primary_reward = primary_reward_count * prp
        secondary_reward = secondary_rp.filter(eligible_su=user.pk).count() * srp
        spot_reward = SpotRewardPoint.objects.filter(eligible_user=user.pk).count() * irp

        data['primary_reward'] = primary_reward
        data['prp_count'] = primary_reward_count
        data['secondary_reward'] = secondary_reward
        data['referral_count'] = referral_count
        data['spot_reward'] = spot_reward

        values = [value for value in [data['primary_reward'], data['secondary_reward'], data['spot_reward']] if
                  value is not None]
        gross = sum(values) if values else None
        data['gross'] = gross
        config = Configuration.objects.all()
        tds = config.get(config_name="TDS").decimal_value
        rtl = config.get(config_name="RTL").decimal_value
        rps = config.get(config_name="RPS").decimal_value
        data['TDS'] = gross * tds
        data['rental'] = gross * rtl
        data['net'] = gross - (data['TDS'] + data['rental'])
        data['repurchase'] = data['net'] * rps
        data['final'] = data['net'] - data['repurchase']
        return data


def team_details_report(current_user):
    team_details = []

    def get_user_details(user, level):
        if level != 0:
            data = {}
            data['level'] = level
            data['user_id'] = user.pk
            data['name'] = user.full_name
            data['mobile_number'] = user.mobile_number.national_number
            data['city'] = user.addresses.first().city if user.addresses.first() else "City Unknown"
            data['referral'] = user.referral_id
            data['status'] = "Active" if user.is_active else "Inactive"
            data['registration_date'] = user.date_joined.date()
            order = Order.objects.filter(user=user).first()
            data['order_placed'] = order.total_amount if order is not None else None
            team_details.append(data)

        # Recursively get user details for the next level
        referrals = User.objects.filter(referral_id=user.pk)
        for referral in referrals:
            get_user_details(referral, level + 1)

    # Start with level 0 for the current user
    get_user_details(current_user, level=0)

    sorted_team_details = sorted(team_details, key=lambda x: x['level'])

    return sorted_team_details


def team_details_tree_report(current_user):
    def referral_list(user):
        data = {
            'user_id': user.pk,
            'name': user.full_name,
            'mobile_number': user.mobile_number.national_number,
            'city': user.addresses.first().city if user.addresses.first() else "City Unknown",
            'referral': user.referral_id,
            'status': "Active" if user.is_active else "Inactive",
            'registration_date': user.date_joined.date(),
            'children': []  # Initialize an empty list for referrals
        }
        order = Order.objects.filter(user_id=user.pk).first()
        data['order_placed'] = order.total_amount if order is not None else None
        return data

    def build_team_tree(user):
        user_data = referral_list(user)
        referrals = User.objects.filter(referral_id=user.pk)

        for referral in referrals:
            referral_data = build_team_tree(referral)  # Recursive call to build referral tree
            user_data['children'].append(referral_data)

        return user_data

    team_details = []

    if current_user is not None:
        # Build the team tree for the current user
        team_tree = build_team_tree(current_user)
        team_details.append(team_tree)

    return team_details


# def primary_reward_criteria_status(user):
#     prp_count = PrimaryRewardPoint.objects.filter(PRP_user=user.pk).count()
#     total_rewards = prp_count * prp
#     claimed_rewards = RewardClaim.objects.filter(user=user.pk).order_by("criteria")
#     rp_criteria = [RPC1, RPC2, RPC3, RPC4]
#     data = {
#         "RP_criteria": None,
#         "RP_compelete": 0,
#         "RP_required": 0,
#         "status": 'in_progress',
#         "claimed_on": None,
#     }
#     response = [data] * len(rp_criteria)
#
#     for i, criteria in enumerate(claimed_rewards):
#         data = {
#             "RP_criteria": rp_criteria[i],
#             "RP_compelete": 0,
#             "RP_required": 0,
#             "status": criteria.status,
#             "claimed_on": str(criteria.claimed_on.date()) if criteria.claimed_on else None,
#         }
#         response[i] = data
#
#     total_rewards_added = False
#
#     for i, criteria in enumerate(rp_criteria):
#         response[i]["RP_criteria"] = criteria
#         if total_rewards < criteria:
#             response[i]["RP_required"] = criteria - total_rewards
#             if not total_rewards_added:
#                 response[i]["RP_compelete"] = total_rewards
#                 response[i]["status"] = "In Progress"
#                 total_rewards_added = True
#
#     return response


def primary_reward_criteria_status(user):
    prp_data = PrimaryRewardPoint.objects.filter(PRP_user=user.pk).values_list('pk', flat=True)
    prp_count = PRPMatching.objects.filter(PRP_id__in=prp_data).count()
    total_rewards = prp_count * prp
    claimed_rewards = RewardClaim.objects.filter(user=user.pk).order_by("criteria")

    # Create RPC criteria dynamically
    rpc_criteria = list(rpc_values.keys())

    RP_complete = [0] * len(rpc_criteria)
    RP_required = [0] * len(rpc_criteria)
    status = ['In-progress'] * len(rpc_criteria)
    claimed_on = [None] * len(rpc_criteria)
    completed_rewards = [None] * len(rpc_criteria)

    for i, criteria in enumerate(claimed_rewards):
        if criteria.claimed_on and criteria.status == 'claimed':
            completed_rewards[i] = criteria.criteria
            claimed_on[i] = criteria.claimed_on.date()
            status[i] = criteria.status
        elif criteria.status == 'completed' or criteria.status == 'skipped':
            status[i] = criteria.status

    for i, reward in enumerate(completed_rewards):
        if reward is not None:
            for j, rpc in enumerate(rpc_criteria):
                if reward == f'RPC{j + 1}':
                    completed_rewards[i] = rpc_values[rpc]
                    total_rewards -= rpc_values[rpc]
                    RP_complete[j] = rpc_values[rpc]

    total_rewards_added = False

    for i, criteria in enumerate(list(rpc_values.values())):
        if total_rewards < criteria and RP_complete[i] != criteria:
            RP_required[i] = criteria - total_rewards
            if not total_rewards_added:
                RP_complete[i] = total_rewards
                total_rewards_added = True
        elif total_rewards >= criteria and status[i] == 'In-progress':
            status[i] = 'Completed'

    result = []

    for i, v in enumerate(rpc_criteria):
        data = {}
        data['mobile_number'] = user.mobile_number.national_number
        data['name'] = user.full_name
        data['RP_criteria'] = list(rpc_values.values())[i]
        data['RP_complete'] = RP_complete[i]
        data['RP_required'] = RP_required[i]
        data['Status'] = status[i]
        data['claimed_on'] = claimed_on[i]
        result.append(data)

    return result
