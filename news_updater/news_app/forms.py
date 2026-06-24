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
        help_texts = {
            'sources': 'Enter up to 7 URLs separated by commas, newlines, or spaces.',
        }
    
    def clean_sources(self):
        sources_text = self.cleaned_data.get('sources')
        if not sources_text:
            return sources_text
            
        # Parse sources similarly to the model method
        import re
        normalized = re.sub(r'[,\n\r\s]+', '|', sources_text)
        sources_list = [source.strip() for source in normalized.split('|') if source.strip()]
        
        if len(sources_list) > 7:
            raise forms.ValidationError(f"You can add a maximum of 7 sources per section. You currently have {len(sources_list)} sources.")
            
        return sources_text

# Delivery times are picked via add-able dropdowns on the dashboard (see
# news_app.views.TIME_CHOICES and update_time_slots), so there is no Django
# form for them anymore.
