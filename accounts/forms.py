from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    first_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'placeholder': 'Your name (optional)'}))

    class Meta:
        model = User
        fields = ['email', 'first_name', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = user.email
        user.first_name = self.cleaned_data.get('first_name', '')
        if commit:
            user.save()
        return user

class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))
