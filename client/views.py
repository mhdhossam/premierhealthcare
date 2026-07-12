from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .serializers import *
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from .models import *
from .permissions import IsPatient
from .services import PaymobService,NotificationService
from core.viewsets import AdminModelViewSet
from datetime import datetime, timedelta




class DepartmentListView(APIView):
    """Step 1: GET /api/wizard/departments/"""
    permission_classes = [AllowAny]

    def get(self, request):
        departments = Department.objects.filter(is_active=True)
        return Response(DepartmentSerializer(departments, many=True).data)


class ServiceListView(APIView):
    """Step 2: GET /api/wizard/departments/<department_id>/services/"""
    permission_classes = [AllowAny]

    def get(self, request, department_id):
        services = Service.objects.filter(department_id=department_id, is_active=True)
        return Response(ServiceSerializer(services, many=True).data)


class BranchListView(APIView):
    """Step 3: GET /api/wizard/services/<service_id>/branches/"""
    permission_classes = [AllowAny]

    def get(self, request, service_id):
        branches = Branch.objects.filter(services__id=service_id, is_active=True).distinct()
        serializer = BranchSerializer(branches, many=True, context={"service_id": service_id})
        return Response(serializer.data)


class DoctorListView(APIView):
    """Step 4: GET /api/wizard/branches/<branch_id>/doctors/?service=<service_id>"""
    permission_classes = [AllowAny]

    def get(self, request, branch_id):
        service_id = request.query_params.get("service")
        if not service_id:
            return Response({"detail": "service query param is required."}, status=400)

        doctors = Doctor.objects.filter(
            branches__id=branch_id,
            services__id=service_id,
        ).distinct()
        serializer = DoctorPublicSerializer(
            doctors, many=True,
            context={"service_id": service_id, "branch_id": branch_id},
        )
        return Response(serializer.data)


class AvailableSlotsView(APIView):
    """
    Step 5: GET /api/wizard/doctors/<doctor_id>/slots/?branch=<branch_id>&date=YYYY-MM-DD

    Computes open slots for one day by taking the doctor's availability
    window at that branch and subtracting already-booked slots.
    """
    permission_classes = [AllowAny]

    def get(self, request, doctor_id):
        branch_id = request.query_params.get("branch")
        date_str = request.query_params.get("date")
        if not branch_id or not date_str:
            return Response({"detail": "branch and date query params are required."}, status=400)

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "date must be YYYY-MM-DD."}, status=400)

        weekday = date.weekday()
        availabilities = DoctorAvailability.objects.filter(
            doctor_id=doctor_id, branch_id=branch_id, weekday=weekday,
        )
        if not availabilities.exists():
            return Response([])

        booked = set(
            Booking.objects.filter(
                doctor_id=doctor_id, branch_id=branch_id, date=date,
                status__in=["pending_payment", "confirmed"],
            ).values_list("start_time", flat=True)
        )

        slots = []
        for avail in availabilities:
            cursor = datetime.combine(date, avail.start_time)
            end = datetime.combine(date, avail.end_time)
            step = timedelta(minutes=avail.slot_duration_minutes)
            while cursor + step <= end:
                if cursor.time() not in booked:
                    slots.append({
                        "date": date,
                        "start_time": cursor.time(),
                        "end_time": (cursor + step).time(),
                    })
                cursor += step

        return Response(AvailableSlotSerializer(slots, many=True).data)
class CreateBookingView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    @transaction.atomic
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        doctor = serializer.validated_data['doctor']
        service = serializer.validated_data['service']
        branch = serializer.validated_data['branch']

        booking = serializer.save(
            patient=request.user.patient_profile,
            fee=self._resolve_fee(doctor, service, branch),
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

        NotificationService.notify_booking_created(booking)

        return Response({
            "booking": BookingSerializer(booking).data,
            "payment_url": result['iframe_url'],
        }, status=status.HTTP_201_CREATED)

    def _resolve_fee(self, doctor: Doctor, service, branch):
        """
        Fee resolution priority: doctor-specific override > branch-specific
        override > service default. This mirrors the same priority the
        wizard's DoctorPublicSerializer.get_effective_fee() uses, so what
        the patient sees in Step 4 is exactly what they're charged.
        """
        ds = DoctorService.objects.filter(doctor=doctor, service=service).first()
        if ds and ds.fee_override is not None:
            return ds.fee_override
        bs = BranchService.objects.filter(branch=branch, service=service).first()
        if bs:
            return bs.effective_fee
        return service.default_fee

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