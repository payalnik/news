from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='news_app/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    
    # Password reset URLs
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='news_app/password_reset.html',
             email_template_name='news_app/password_reset_email.html',
             subject_template_name='news_app/password_reset_subject.txt'
         ), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='news_app/password_reset_done.html'
         ), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='news_app/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='news_app/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
    
    path('verify-email/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('add-news-section/', views.add_news_section, name='add_news_section'),
    path('edit-news-section/<int:section_id>/', views.edit_news_section, name='edit_news_section'),
    path('delete-news-section/<int:section_id>/', views.delete_news_section, name='delete_news_section'),
    path('update-section-order/', views.update_section_order, name='update_section_order'), # Added URL for reordering
    path('update-time-slots/', views.update_time_slots, name='update_time_slots'),
    path('send-now/', views.send_now, name='send_now'),
    path('news-history/', views.news_history, name='news_history'),
    path('news-history/<int:section_id>/', views.news_history, name='news_history_section'),
]
