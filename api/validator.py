from django.core.exceptions import ValidationError
from phonenumber_field.phonenumber import to_python
from phonenumbers.phonenumberutil import is_possible_number


def validate_possible_number(phone):
    phone_number = to_python(phone)
    if (
            phone_number
            and not is_possible_number(phone_number)
            or not phone_number.is_valid()
    ):
        if phone_number is not None and hasattr(phone_number, 'national_number') and \
                phone_number.national_number is not None:
            national_number = str(phone_number.national_number)
            if len(national_number) == 10:
                return phone_number
        raise ValidationError(
            "The phone number entered is not valid."
        )
    return phone_number
