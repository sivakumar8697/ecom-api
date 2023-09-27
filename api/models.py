from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import BaseUserManager
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from .utils import generate_otp, generate_user_id
from .validator import validate_possible_number

GENDER = (('male', 'male'),
          ('female', 'female'),
          ('others', 'others'))

# SIZE_CHOICES = (
#     ('S', 'Small'),
#     ('M', 'Medium'),
#     ('L', 'Large'),
#     ('XL', 'Extra Large'),  # No choices needed
# )

REWARD_CATEGORIES = [
    ('first_join', 'first_join'),
    ('first_reward', 'first_reward')
]

REWARD_CLAIM = (
    ('in_progress', 'in_progress'),
    ('completed', 'completed'),
    ('claimed', 'claimed'),
    ('skipped', 'skipped'),
    ('delivered', 'delivered')
)

PROOF = (('ID1', 'ID1'),
         ('ID2', 'ID2'))


class PossiblePhoneNumberField(PhoneNumberField):
    """Less strict field for phone numbers written to database."""
    default_validators = [validate_possible_number]


class UserManager(BaseUserManager):
    def create_user(self, mobile_number, otp, **extra_fields):
        if not mobile_number:
            raise ValueError('The Mobile Number field must be set')
        user = self.model(mobile_number=mobile_number, otp=otp, **extra_fields)
        user.set_password(otp)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, otp=generate_otp()[1], **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(mobile_number, otp, **extra_fields)


class User(AbstractUser):
    full_name = models.CharField(blank=True, null=True, max_length=250)
    gender = models.CharField(choices=GENDER, max_length=20, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    mobile_number = PossiblePhoneNumberField(blank=True, default="", unique=True)
    pan = models.CharField(max_length=100, unique=True, blank=True, null=True)
    otp = models.CharField(blank=True, null=True, max_length=256)
    validity = models.DateTimeField(blank=True, null=True)
    hash = models.CharField(blank=True, null=True, max_length=100)
    is_verified = models.BooleanField(default=False)
    is_updated = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_free = models.BooleanField(default=True)
    order_complete = models.BooleanField(default=False)
    referral_id = models.CharField(blank=True, null=True,
                                   max_length=250)  # (editable=False) will make this as one-time-writable field
    username = None

    USERNAME_FIELD = 'mobile_number'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return str(self.mobile_number)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.pk = generate_user_id(self.date_joined, self.mobile_number)
        super().save(*args, **kwargs)

    @property
    def simple_mobile_number(self):
        return self.mobile_number.national_number

    @property
    def addresses(self):
        return self.addresses.all()


class Configuration(models.Model):
    config_name = models.CharField(max_length=100, unique=True, null=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    decimal_value = models.DecimalField(max_digits=12, decimal_places=6, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Convert percentage value to decimal value
        if self.value is not None:
            self.decimal_value = Decimal(self.value) / Decimal(100)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.config_name


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255)
    landmark = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.address_line1}, {self.city}"


class Order(models.Model):
    order_id = models.AutoField(primary_key=True)
    date_of_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_order')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_tax = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    invoice_number = models.CharField(max_length=20, unique=True, null=True,
                                      help_text="Invoice number starting with 'M' and 8 digits.")
    delivered_on = models.DateField(null=True, blank=True, help_text="Date when the order was delivered.")
    delivery_partner = models.CharField(max_length=255, null=True, blank=True, help_text="Delivery partner's name.")
    payment_status = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, null=True, blank=True)
    @property
    def order_items(self):
        return self.order_items.all()

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate a new invoice number if it doesn't already exist
            last_order = Order.objects.order_by('-date_of_transaction').first()
            if last_order:
                last_invoice_number = last_order.invoice_number
                if last_invoice_number:
                    # Extract the numeric part and increment it
                    last_number = int(last_invoice_number[1:])
                    new_number = last_number + 1
                    new_invoice_number = f"M{new_number:07d}"  # Format to 7 digits with 'M' prefix
                else:
                    # If the last invoice number is invalid, start from 'M00000001'
                    new_invoice_number = "M0000001"
            else:
                # If there are no previous orders, start from 'M00000001'
                new_invoice_number = "M0000001"

            self.invoice_number = new_invoice_number

        super().save(*args, **kwargs)


class OrderItem(models.Model):
    item_line_no = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    product_group = models.CharField(max_length=255, default="Garments")
    product_category = models.CharField(max_length=255, default="T-shirts")
    description = models.CharField(max_length=1000)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    tax = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    quantity = models.IntegerField()
    size = models.CharField(max_length=50)


class PrimaryRewardPoint(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    PRP_user = models.ForeignKey(User, on_delete=models.CASCADE)
    referred_by = models.CharField(blank=True, null=True, max_length=100)
    new_user = models.CharField(blank=True, null=True, max_length=100)
    matching_count = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f'{self.PRP_user} - {self.date}'


class PRPMatching(models.Model):
    PRP_id = models.ForeignKey(PrimaryRewardPoint, on_delete=models.CASCADE)
    matching_user1 = models.CharField(blank=True, null=True, max_length=100)
    matching_user2 = models.CharField(blank=True, null=True, max_length=100)

    def __str__(self):
        return f'{self.matching_user1} - {self.matching_user2}'


class SecondaryRewardPoint(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    PRP_id = models.ForeignKey(PrimaryRewardPoint, on_delete=models.CASCADE)
    referred_su1 = models.CharField(blank=True, null=True, max_length=100)
    referred_su2 = models.CharField(blank=True, null=True, max_length=100)
    eligible_su = models.ForeignKey(User, on_delete=models.CASCADE, related_name='eligible_su')
    reward_category = models.CharField(max_length=100, choices=REWARD_CATEGORIES)

    def __str__(self):
        return f'{self.eligible_su}'


class SpotRewardPoint(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    eligible_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='eligible_user')
    referral = models.CharField(blank=True, null=True, max_length=100)

    def __str__(self):
        return f'{self.eligible_user}'


class Payout(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payout_user')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    prp_team_count = models.IntegerField()
    primary_rp = models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=2)
    secondary_rp = models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=2)
    referral_count = models.IntegerField()
    spot_rp = models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=2)
    gross = models.DecimalField(max_digits=10, decimal_places=2)
    tds = models.DecimalField(max_digits=10, decimal_places=2)
    rental = models.DecimalField(max_digits=10, decimal_places=2)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    repurchase = models.DecimalField(max_digits=10, decimal_places=2)
    final = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        primary_rp = self.primary_rp
        secondary_rp = self.secondary_rp
        spot_rp = self.spot_rp

        values = [value for value in [primary_rp, secondary_rp, spot_rp] if value is not None]
        gross = sum(values) if values else None

        if gross is not None:
            config = Configuration.objects.all()
            tds = config.get(config_name="TDS").decimal_value
            rtl = config.get(config_name="RTL").decimal_value
            rps = config.get(config_name="RPS").decimal_value
            self.gross = gross
            self.tds = self.gross * tds
            self.rental = self.gross * rtl
            self.net = self.gross - (self.tds + self.rental)
            self.repurchase = self.net * rps
            self.final = self.net - self.repurchase

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user}'s Payout Details"


class ReferralReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_user')
    total_sales = models.IntegerField()
    sales_considered = models.IntegerField()
    sales_carry_forwarded = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}'s Referral Details"


CRITERIA = (('RPC1', 'RPC1'),
            ('RPC2', 'RPC2'),
            ('RPC3', 'RPC3'),
            ('RPC4', 'RPC4'))


class RewardClaim(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reward_claim_user')
    status = models.CharField(choices=REWARD_CLAIM, max_length=20, blank=True, null=True)
    claimed_on = models.DateTimeField(null=True, blank=True)
    criteria = models.CharField(choices=CRITERIA, max_length=20, blank=True, null=True)

    def __str__(self):
        return f"{self.user} -- {self.criteria}"


class BankDetail(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_details_user')
    account_holder_name = models.CharField(max_length=255)
    account_no = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=50)
    account_type = models.CharField(max_length=50)
    branch = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.full_name}'s Bank Details"


class KYCImage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_user')
    image = models.ImageField(upload_to='images/')
    proof_type = models.CharField(choices=PROOF, max_length=20)
