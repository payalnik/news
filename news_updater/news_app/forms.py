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
    # Morning: 6:00 AM - 11:30 AM
    morning_slots = forms.MultipleChoiceField(
        choices=[(f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}") 
                for hour in range(6, 12) 
                for minute in (0, 30)],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Morning (6:00 - 11:30)"
    )
    
    # Afternoon: 12:00 PM - 5:30 PM
    afternoon_slots = forms.MultipleChoiceField(
        choices=[(f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}") 
                for hour in range(12, 18) 
                for minute in (0, 30)],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Afternoon (12:00 - 17:30)"
    )
    
    # Evening: 6:00 PM - 11:30 PM
    evening_slots = forms.MultipleChoiceField(
        choices=[(f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}") 
                for hour in range(18, 24) 
                for minute in (0, 30)],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Evening (18:00 - 23:30)"
    )
    
    # Night: 12:00 AM - 5:30 AM
    night_slots = forms.MultipleChoiceField(
        choices=[(f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}") 
                for hour in range(0, 6) 
                for minute in (0, 30)],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Night (00:00 - 05:30)"
    )
    
    def get_all_selected_slots(self):
        """Combine all selected time slots from different time periods"""
        all_slots = []
        if hasattr(self, 'cleaned_data'):
            all_slots.extend(self.cleaned_data.get('morning_slots', []))
            all_slots.extend(self.cleaned_data.get('afternoon_slots', []))
            all_slots.extend(self.cleaned_data.get('evening_slots', []))
            all_slots.extend(self.cleaned_data.get('night_slots', []))
        return all_slots
