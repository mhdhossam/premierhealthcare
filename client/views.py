# views.py
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import RoleTokenObtainPairSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Booking, Payment, BookingStatus, PaymentStatus, Doctor
from .serializers import BookingCreateSerializer, BookingSerializer
from .permissions import IsPatient
from .services import PaymobService


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

        return Response({
            "booking": BookingSerializer(booking).data,
            "payment_url": result['iframe_url'],
        }, status=status.HTTP_201_CREATED)

    def _get_fee(self, doctor: Doctor):
        return getattr(doctor, 'consultation_fee', 300)  # add this field to Doctor if variable pricing


class PaymobWebhookView(APIView):
    permission_classes = [AllowAny]

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

        booking = get_object_or_404(Booking, id=merchant_order_id)
        payment = get_object_or_404(Payment, booking=booking)
        payment.raw_webhook_payload = request.data
        payment.paymob_transaction_id = obj.get("id")

        if success:
            payment.status = PaymentStatus.PAID
            from django.utils import timezone
            payment.paid_at = timezone.now()
            booking.status = BookingStatus.CONFIRMED
        else:
            payment.status = PaymentStatus.FAILED
            booking.status = BookingStatus.CANCELLED

        payment.save()
        booking.save()

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