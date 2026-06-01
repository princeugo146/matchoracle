from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'placeholder': 'your@email.com',
            'autofocus': True,
        })
    )


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'At least 8 characters'}),
        min_length=8,
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat your new password'}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError('Passwords do not match.')
        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                raise ValidationError(list(e.messages))
        return cleaned
