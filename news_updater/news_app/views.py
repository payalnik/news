from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import datetime

from .models import UserProfile, NewsSection, TimeSlot, VerificationCode
from .forms import SignUpForm, VerificationForm, NewsSectionForm, TimeSlotForm
from .tasks import send_news_update

def home(request):
    return render(request, 'news_app/home.html')

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            user_profile = UserProfile.objects.create(user=user)
            
            # Generate verification code
            code = VerificationCode.generate_code()
            VerificationCode.objects.create(user_profile=user_profile, code=code)
            
            # Send verification email
            subject = 'Verify your email for News Updater'
            message = f'Your verification code is: {code}'
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [user.email]
            send_mail(subject, message, from_email, recipient_list)
            
            login(request, user)
            return redirect('verify_email')
    else:
        form = SignUpForm()
    return render(request, 'news_app/signup.html', {'form': form})

@login_required
def verify_email(request):
    user_profile = request.user.profile
    
    if user_profile.email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = VerificationForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            verification = VerificationCode.objects.filter(
                user_profile=user_profile,
                code=code,
                is_used=False,
                created_at__gte=timezone.now() - timezone.timedelta(days=1)
            ).first()
            
            if verification:
                verification.is_used = True
                verification.save()
                user_profile.email_verified = True
                user_profile.save()
                messages.success(request, 'Email verified successfully!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid or expired verification code.')
    else:
        form = VerificationForm()
    
    return render(request, 'news_app/verify_email.html', {'form': form})

@login_required
def resend_verification(request):
    user_profile = request.user.profile
    
    if user_profile.email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('dashboard')
    
    # Generate new verification code
    code = VerificationCode.generate_code()
    VerificationCode.objects.create(user_profile=user_profile, code=code)
    
    # Send verification email
    subject = 'Verify your email for News Updater'
    message = f'Your verification code is: {code}'
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [request.user.email]
    send_mail(subject, message, from_email, recipient_list)
    
    messages.success(request, 'A new verification code has been sent to your email.')
    return redirect('verify_email')

@login_required
def dashboard(request):
    user_profile = request.user.profile
    
    if not user_profile.email_verified:
        messages.warning(request, 'Please verify your email first.')
        return redirect('verify_email')
    
    news_sections = NewsSection.objects.filter(user_profile=user_profile)
    
    # Get all time slots for the user
    time_slots = TimeSlot.objects.filter(user_profile=user_profile)
    selected_slots = [slot.time.strftime('%H:%M') for slot in time_slots]
    
    time_slot_form = TimeSlotForm(initial={'time_slots': selected_slots})
    
    return render(request, 'news_app/dashboard.html', {
        'news_sections': news_sections,
        'time_slot_form': time_slot_form,
    })

@login_required
def add_news_section(request):
    user_profile = request.user.profile
    
    if not user_profile.email_verified:
        messages.warning(request, 'Please verify your email first.')
        return redirect('verify_email')
    
    if request.method == 'POST':
        form = NewsSectionForm(request.POST)
        if form.is_valid():
            news_section = form.save(commit=False)
            news_section.user_profile = user_profile
            news_section.save()
            messages.success(request, 'News section added successfully!')
            return redirect('dashboard')
    else:
        form = NewsSectionForm()
    
    return render(request, 'news_app/add_news_section.html', {'form': form})

@login_required
def edit_news_section(request, section_id):
    user_profile = request.user.profile
    news_section = get_object_or_404(NewsSection, id=section_id, user_profile=user_profile)
    
    if request.method == 'POST':
        form = NewsSectionForm(request.POST, instance=news_section)
        if form.is_valid():
            form.save()
            messages.success(request, 'News section updated successfully!')
            return redirect('dashboard')
    else:
        form = NewsSectionForm(instance=news_section)
    
    return render(request, 'news_app/edit_news_section.html', {'form': form, 'section': news_section})

@login_required
def delete_news_section(request, section_id):
    user_profile = request.user.profile
    news_section = get_object_or_404(NewsSection, id=section_id, user_profile=user_profile)
    
    if request.method == 'POST':
        news_section.delete()
        messages.success(request, 'News section deleted successfully!')
        return redirect('dashboard')
    
    return render(request, 'news_app/delete_news_section.html', {'section': news_section})

@login_required
def update_time_slots(request):
    user_profile = request.user.profile
    
    if request.method == 'POST':
        form = TimeSlotForm(request.POST)
        if form.is_valid():
            selected_slots = form.cleaned_data['time_slots']
            
            # Delete existing time slots
            TimeSlot.objects.filter(user_profile=user_profile).delete()
            
            # Create new time slots
            for slot in selected_slots:
                hour, minute = map(int, slot.split(':'))
                time = datetime.strptime(f"{hour}:{minute}", "%H:%M").time()
                TimeSlot.objects.create(user_profile=user_profile, time=time)
            
            messages.success(request, 'Time slots updated successfully!')
    
    return redirect('dashboard')

@login_required
def send_now(request):
    user_profile = request.user.profile
    
    if not user_profile.email_verified:
        messages.warning(request, 'Please verify your email first.')
        return redirect('verify_email')
    
    # Check if user has any news sections
    news_sections = NewsSection.objects.filter(user_profile=user_profile)
    if not news_sections.exists():
        messages.warning(request, 'Please add at least one news section first.')
        return redirect('dashboard')
    
    # Trigger the Celery task to send news update
    send_news_update.delay(user_profile.id)
    
    messages.success(request, 'News update has been queued and will be sent shortly.')
    return redirect('dashboard')
