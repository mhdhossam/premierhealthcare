from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .serializers import RoleTokenObtainPairSerializer, NotificationSerializer,BookingCreateSerializer, BookingSerializer,AdminTokenObtainPairSerializer, AdminUserSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from .models import Booking, Payment, BookingStatus, PaymentStatus, Doctor, Notification , CustomUser
from .permissions import IsPatient
from .services import PaymobService,NotificationService
from core.viewsets import AdminModelViewSet



class CreateBookingView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    @transaction.atomic
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = serializer.save(
            patient=request.user.patient_profile,
            fee=self._get_fee(serializer.validated_data['doctor']),
        )

        paymob = PaymobService()
        try:
            result = paymob.init_payment(booking, request.user)
        except Exception as e:
            booking.delete()
            return Response({"detail": f"Payment init failed: {str(e)}"},
                             status=status.HTTP_502_BAD_GATEWAY)

        Payment.objects.create(
            booking=booking,
            amount=booking.fee,
            paymob_order_id=result['order_id'],
            payment_token=result['payment_token'],
        )

        # notify both sides that a booking request was made
        NotificationService.notify_booking_created(booking)

        return Response({
            "booking": BookingSerializer(booking).data,
            "payment_url": result['iframe_url'],
        }, status=status.HTTP_201_CREATED)

    def _get_fee(self, doctor: Doctor):
        return getattr(doctor, 'consultation_fee', 300)


class PaymobWebhookView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        hmac_received = request.query_params.get("hmac")
        if not hmac_received:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        paymob = PaymobService()
        if not paymob.verify_hmac(request.data, hmac_received):
            return Response({"detail": "Invalid HMAC"}, status=status.HTTP_403_FORBIDDEN)

        obj = request.data.get("obj", request.data)
        merchant_order_id = obj.get("order", {}).get("merchant_order_id")
        success = obj.get("success")

        if not merchant_order_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        booking = get_object_or_404(
            Booking.objects.select_related("patient__user", "doctor__user"),
            id=merchant_order_id,
        )
        payment = get_object_or_404(Payment, booking=booking)
        payment.raw_webhook_payload = request.data
        payment.paymob_transaction_id = obj.get("id")

        if success:
            payment.status = PaymentStatus.PAID
            payment.paid_at = timezone.now()
            booking.status = BookingStatus.CONFIRMED
            payment.save()
            booking.save()
            NotificationService.notify_booking_confirmed(booking)
        else:
            payment.status = PaymentStatus.FAILED
            booking.status = BookingStatus.CANCELLED
            payment.save()
            booking.save()
            NotificationService.notify_booking_cancelled(booking, reason="Payment failed")

        return Response(status=status.HTTP_200_OK)


class MyBookingsView(generics.ListAPIView):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'patient':
            return Booking.objects.filter(patient=user.patient_profile).order_by('-date')
        elif user.role == 'doctor':
            return Booking.objects.filter(doctor=user.doctor_profile).order_by('-date')
        return Booking.objects.none()


class RoleTokenObtainPairView(TokenObtainPairView):
    serializer_class = RoleTokenObtainPairSerializer


# --- Notification endpoints ---

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Notification.objects.filter(recipient=self.request.user)
            .select_related("booking")
        )


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        # scoped to request.user to prevent IDOR — a user can't mark
        # someone else's notification as read by guessing a UUID
        updated = Notification.objects.filter(
            pk=pk, recipient=request.user
        ).update(is_read=True)
        if not updated:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_200_OK)


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True)
        return Response(status=status.HTTP_200_OK)
    

class AdminTokenObtainPairView(TokenObtainPairView):
    """Login endpoint — returns access + refresh + user profile."""
    serializer_class = AdminTokenObtainPairSerializer


# class AdminTokenVerifyView(TokenVerifyView):
#     """Verify token validity. Returns 200 if valid, 401 if not."""
#     pass


class AdminLogoutView(APIView):
    """
    Blacklists the refresh token on logout.
    Requires: { "refresh": "<token>" } in body.
    """
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminUserViewSet(AdminModelViewSet):
    """
    CRUD for admin user management.
    Only superusers can manage other users.
    """
    queryset = CustomUser.objects.filter(is_staff=True).order_by("-id")
    serializer_class = AdminUserSerializer
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username"]

    def get_permissions(self):
        # Creating/deleting users requires superuser
        from rest_framework.permissions import IsAdminUser
        from core.permissions import IsSuperUser
        if self.action in ("create", "destroy"):
            return [IsSuperUser()]
        return [IsAdminUser()]    