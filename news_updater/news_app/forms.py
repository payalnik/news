from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import NewsSection, TimeSlot, VerificationCode

class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, required=True, help_text='Required. Enter a valid email address.')
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

class VerificationForm(forms.Form):
    code = forms.CharField(max_length=6, required=True, help_text='Enter the 6-digit verification code sent to your email.')

class NewsSectionForm(forms.ModelForm):
    class Meta:
        model = NewsSection
        fields = ('name', 'sources', 'prompt')
        widgets = {
            'prompt': forms.Textarea(attrs={'rows': 4}),
            'sources': forms.Textarea(attrs={'rows': 3, 'placeholder': 'https://example.com, https://another-source.com'}),
        }

class TimeSlotForm(forms.Form):
    HOUR_CHOICES = [(i, f"{i:02d}") for i in range(24)]
    MINUTE_CHOICES = [(i*30, f"{i*30:02d}") for i in range(2)]  # 00 and 30
    
    time_slots = forms.MultipleChoiceField(
        choices=[(f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}") 
                for hour in range(24) 
                for minute in (0, 30)],
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
