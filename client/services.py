import requests
from django.conf import settings


class PaymobService:
    BASE_URL = "https://accept.paymob.com/api"

    def __init__(self):
        self.api_key = settings.PAYMOB_API_KEY
        self.integration_id = settings.PAYMOB_INTEGRATION_ID
        self.iframe_id = settings.PAYMOB_IFRAME_ID
        self.hmac_secret = settings.PAYMOB_HMAC_SECRET
        self._auth_token = None

    def authenticate(self):
        resp = requests.post(f"{self.BASE_URL}/auth/tokens", json={"api_key": self.api_key})
        resp.raise_for_status()
        self._auth_token = resp.json()["token"]
        return self._auth_token

    def create_order(self, amount_cents, merchant_order_id, items=None):
        resp = requests.post(f"{self.BASE_URL}/ecommerce/orders", json={
            "auth_token": self._auth_token,
            "delivery_needed": False,
            "amount_cents": amount_cents,
            "currency": "EGP",
            "merchant_order_id": merchant_order_id,
            "items": items or [],
        })
        resp.raise_for_status()
        return resp.json()

    def generate_payment_key(self, order_id, amount_cents, billing_data):
        resp = requests.post(f"{self.BASE_URL}/acceptance/payment_keys", json={
            "auth_token": self._auth_token,
            "amount_cents": amount_cents,
            "expiration": 3600,
            "order_id": order_id,
            "billing_data": billing_data,
            "currency": "EGP",
            "integration_id": self.integration_id,
        })
        resp.raise_for_status()
        return resp.json()["token"]

    def get_iframe_url(self, payment_token):
        return f"https://accept.paymob.com/api/acceptance/iframes/{self.iframe_id}?payment_token={payment_token}"

    def init_payment(self, booking, patient_user):
        self.authenticate()
        amount_cents = int(booking.fee * 100)

        order = self.create_order(
            amount_cents=amount_cents,
            merchant_order_id=str(booking.id),
            items=[{
                "name": f"Appointment with {booking.doctor}",
                "amount_cents": amount_cents,
                "quantity": 1,
            }]
        )

        billing_data = {
            "first_name": patient_user.username,
            "last_name": "N/A",
            "email": patient_user.email,
            "phone_number": getattr(patient_user.patient_profile, 'phone_number', 'NA') or "NA",
            "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA",
            "shipping_method": "NA", "postal_code": "NA", "city": "NA",
            "country": "EG", "state": "NA",
        }

        token = self.generate_payment_key(order["id"], amount_cents, billing_data)
        return {
            "order_id": order["id"],
            "payment_token": token,
            "iframe_url": self.get_iframe_url(token),
        }

    def verify_hmac(self, data: dict, received_hmac: str) -> bool:
        import hmac, hashlib
        ordered_keys = [
            "amount_cents", "created_at", "currency", "error_occured",
            "has_parent_transaction", "id", "integration_id", "is_3d_secure",
            "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
            "is_voided", "order.id", "owner", "pending", "source_data.pan",
            "source_data.sub_type", "source_data.type", "success",
        ]
        obj = data.get("obj", data)
        concat_str = ""
        for key in ordered_keys:
            if "." in key:
                parent, child = key.split(".")
                val = obj.get(parent, {}).get(child, "")
            else:
                val = obj.get(key, "")
            concat_str += str(val).lower() if isinstance(val, bool) else str(val)

        computed = hmac.new(
            self.hmac_secret.encode(), concat_str.encode(), hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed, received_hmac)