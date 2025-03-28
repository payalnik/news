from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.backends import ModelBackend
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import datetime
import logging
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction

from .models import UserProfile, NewsSection, TimeSlot, VerificationCode, NewsItem
from django.core.paginator import Paginator
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
            
            # Specify the backend when logging in the user
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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
    
    # Get client timezone from cookie
    client_timezone = request.COOKIES.get('client_timezone')
    
    # Default to server timezone if client timezone is not available
    if not client_timezone:
        client_timezone = settings.TIME_ZONE
    
    # Convert UTC times to client timezone
    selected_slots = []
    for slot in time_slots:
        # Create a datetime object with today's date and the UTC time
        utc_date = timezone.now().astimezone(timezone.utc).date()
        utc_dt = timezone.datetime.combine(utc_date, slot.time)
        utc_dt = timezone.make_aware(utc_dt, timezone.utc)
        
        try:
            # Convert to client timezone
            import pytz
            client_tz = pytz.timezone(client_timezone)
            local_dt = utc_dt.astimezone(client_tz)
            
            # Format as HH:MM
            selected_slots.append(local_dt.strftime('%H:%M'))
        except Exception as e:
            # If there's an error with the timezone, fall back to the server's timezone
            logger = logging.getLogger(__name__)
            logger.error(f"Error converting timezone {client_timezone}: {str(e)}")
            
            # Fall back to server timezone
            local_dt = timezone.localtime(utc_dt)
            selected_slots.append(local_dt.strftime('%H:%M'))
    
    # Organize selected slots by time of day
    morning_slots = [slot for slot in selected_slots if 6 <= int(slot.split(':')[0]) < 12]
    afternoon_slots = [slot for slot in selected_slots if 12 <= int(slot.split(':')[0]) < 18]
    evening_slots = [slot for slot in selected_slots if 18 <= int(slot.split(':')[0]) < 24]
    night_slots = [slot for slot in selected_slots if 0 <= int(slot.split(':')[0]) < 6]
    
    time_slot_form = TimeSlotForm(initial={
        'morning_slots': morning_slots,
        'afternoon_slots': afternoon_slots,
        'evening_slots': evening_slots,
        'night_slots': night_slots
    })
    
    return render(request, 'news_app/dashboard.html', {
        'news_sections': news_sections,
        'time_slot_form': time_slot_form,
    })

@login_required
@require_POST # Ensure this view only accepts POST requests
@transaction.atomic # Ensure database operations are atomic
def update_section_order(request):
    user_profile = request.user.profile
    try:
        data = json.loads(request.body)
        section_ids = data.get('order', [])
        
        # Validate that all IDs are integers
        try:
            section_ids = [int(id_str) for id_str in section_ids]
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid section IDs provided.'}, status=400)

        # Fetch the sections belonging to the user to ensure ownership and existence
        sections = NewsSection.objects.filter(user_profile=user_profile, id__in=section_ids)
        sections_map = {section.id: section for section in sections}

        # Check if all provided IDs correspond to valid sections for this user
        if len(sections_map) != len(section_ids):
             return JsonResponse({'status': 'error', 'message': 'One or more section IDs are invalid or do not belong to the user.'}, status=400)

        # Update the order based on the received list
        for index, section_id in enumerate(section_ids):
            section = sections_map[section_id]
            section.order = index
            section.save(update_fields=['order'])
            
        return JsonResponse({'status': 'success', 'message': 'Section order updated successfully.'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        # Log the error for debugging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating section order for user {user_profile.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

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
            # Get all selected time slots from all time periods
            selected_slots = form.get_all_selected_slots()
            
            # Delete existing time slots
            TimeSlot.objects.filter(user_profile=user_profile).delete()
            
            # Get client timezone from the form or cookie
            client_timezone = request.POST.get('client_timezone')
            if not client_timezone:
                # Try to get from cookie
                client_timezone = request.COOKIES.get('client_timezone')
            
            # Default to server timezone if client timezone is not available
            if not client_timezone:
                client_timezone = settings.TIME_ZONE
                
            # Create new time slots
            for slot in selected_slots:
                hour, minute = map(int, slot.split(':'))
                
                # Create a datetime object with today's date and the selected time
                naive_dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                try:
                    # Make it timezone-aware using the client's timezone
                    import pytz
                    client_tz = pytz.timezone(client_timezone)
                    local_dt = client_tz.localize(naive_dt)
                    
                    # Convert to UTC
                    utc_dt = local_dt.astimezone(timezone.utc)
                    
                    # Extract the time component
                    utc_time = utc_dt.time()
                    
                    # Create the time slot with the UTC time
                    TimeSlot.objects.create(user_profile=user_profile, time=utc_time)
                    
                    # Log for debugging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Created time slot: {hour}:{minute} in {client_timezone} -> {utc_time} UTC")
                except Exception as e:
                    # If there's an error with the timezone, fall back to the server's timezone
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting timezone {client_timezone}: {str(e)}")
                    
                    # Fall back to server timezone
                    local_dt = timezone.localtime(timezone.now()).replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if timezone.is_naive(local_dt):
                        local_dt = timezone.make_aware(local_dt)
                    utc_dt = local_dt.astimezone(timezone.utc)
                    utc_time = utc_dt.time()
                    TimeSlot.objects.create(user_profile=user_profile, time=utc_time)
            
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

@login_required
def news_history(request, section_id=None):
    user_profile = request.user.profile
    
    if not user_profile.email_verified:
        messages.warning(request, 'Please verify your email first.')
        return redirect('verify_email')
    
    # Get all news sections for the user
    news_sections = NewsSection.objects.filter(user_profile=user_profile)
    
    if not news_sections.exists():
        messages.warning(request, 'Please add at least one news section first.')
        return redirect('dashboard')
    
    # If section_id is provided, filter by that section, otherwise show all
    if section_id:
        section = get_object_or_404(NewsSection, id=section_id, user_profile=user_profile)
        news_items = NewsItem.objects.filter(user_profile=user_profile, news_section=section)
        current_section = section
    else:
        news_items = NewsItem.objects.filter(user_profile=user_profile)
        current_section = None
    
    # Order by most recent first
    news_items = news_items.order_by('-created_at')
    
    # Paginate the results
    paginator = Paginator(news_items, 10)  # Show 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Process the sources for each news item for display
    for item in page_obj:
        try:
            item.sources_list = json.loads(item.sources)
        except:
            item.sources_list = []
    
    return render(request, 'news_app/news_history.html', {
        'page_obj': page_obj,
        'news_sections': news_sections,
        'current_section': current_section,
    })
