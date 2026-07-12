# urls.py
from django.urls import path
from .views import *
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"users", AdminUserViewSet, basename="admin-user")




urlpatterns = [
    path('token/', RoleTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('bookings/create/', CreateBookingView.as_view(), name='booking-create'),
    path('bookings/mine/', MyBookingsView.as_view(), name='booking-mine'),
    path('payments/webhook/', PaymobWebhookView.as_view(), name='paymob-webhook'),
    
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<uuid:pk>/read/", MarkNotificationReadView.as_view(), name="notification-mark-read"),
    path("notifications/read-all/", MarkAllNotificationsReadView.as_view(), name="notification-mark-all-read"),


    path("wizard/departments/", DepartmentListView.as_view(), name="wizard-departments"),
    path("wizard/departments/<int:department_id>/services/", ServiceListView.as_view(), name="wizard-services"),
    path("wizard/services/<int:service_id>/branches/", BranchListView.as_view(), name="wizard-branches"),
    path("wizard/branches/<int:branch_id>/doctors/", DoctorListView.as_view(), name="wizard-doctors"),
    path("wizard/doctors/<int:doctor_id>/slots/", AvailableSlotsView.as_view(), name="wizard-slots"),
]+ router.urls
# urls.py — add to your existing urlpatterns list (append, don't reassign — see the earlier urlpatterns overwrite bug)



