from django.contrib import admin

from api.models import User, Order, OrderItem, Address, PrimaryRewardPoint, PRPMatching, SecondaryRewardPoint, Payout, \
    Configuration, RewardClaim, BankDetail, KYCImage

# Register your models here.
admin.site.register(User)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Address)
admin.site.register(PrimaryRewardPoint)
admin.site.register(PRPMatching)
admin.site.register(SecondaryRewardPoint)
admin.site.register(Payout)
admin.site.register(Configuration)
admin.site.register(RewardClaim)
admin.site.register(BankDetail)
admin.site.register(KYCImage)
