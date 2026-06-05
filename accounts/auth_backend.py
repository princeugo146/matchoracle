from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows staff to log in to the Django
    admin using either their email address or their username.

    Django's admin login form submits the value under the key that matches
    USERNAME_FIELD (which is 'email' on this project's User model).  This
    backend intercepts that value and tries both fields so that an account
    created with ``createsuperuser`` (which sets a username) can still be
    accessed even if the operator types the username into the email box.

    Lookup order:
      1. Exact email match  (case-insensitive)
      2. Exact username match (case-insensitive)

    If more than one account somehow matches (shouldn't happen given the
    unique constraints) we fall back to None for safety.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        if username is None:
            # Django may pass the value under the USERNAME_FIELD key ('email')
            username = kwargs.get(UserModel.USERNAME_FIELD)

        if username is None or password is None:
            return None

        try:
            # Try email first, then username — both are unique on the model.
            user = UserModel.objects.get(
                Q(email__iexact=username) | Q(username__iexact=username)
            )
        except UserModel.DoesNotExist:
            # Run the default password hasher to mitigate timing attacks.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
