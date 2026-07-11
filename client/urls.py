# urls.py
from django.urls import path
from .views import NotificationListView, RoleTokenObtainPairView, CreateBookingView, PaymobWebhookView, MyBookingsView, MarkNotificationReadView,MarkAllNotificationsReadView 
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path('token/', RoleTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('bookings/create/', CreateBookingView.as_view(), name='booking-create'),
    path('bookings/mine/', MyBookingsView.as_view(), name='booking-mine'),
    path('payments/webhook/', PaymobWebhookView.as_view(), name='paymob-webhook'),
    
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<uuid:pk>/read/", MarkNotificationReadView.as_view(), name="notification-mark-read"),
    path("notifications/read-all/", MarkAllNotificationsReadView.as_view(), name="notification-mark-all-read"),
]