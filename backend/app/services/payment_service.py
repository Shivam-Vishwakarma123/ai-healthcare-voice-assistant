from typing import Any, Protocol

import httpx


class PaymentProviderError(Exception):
    pass


class PaymentService(Protocol):
    async def create_order(
        self,
        *,
        invoice_id: int,
        invoice_number: str,
        amount_minor: int,
        currency: str,
    ) -> str: ...

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...


class RazorpayPaymentService:
    def __init__(self, key_id: str, key_secret: str, api_base_url: str):
        self.key_id = key_id
        self.key_secret = key_secret
        self.api_base_url = api_base_url.rstrip("/")

    async def create_order(
        self,
        *,
        invoice_id: int,
        invoice_number: str,
        amount_minor: int,
        currency: str,
    ) -> str:
        try:
            async with httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=httpx.Timeout(15.0, connect=5.0),
            ) as client:
                response = await client.post(
                    f"{self.api_base_url}/orders",
                    json={
                        "amount": amount_minor,
                        "currency": currency,
                        "receipt": invoice_number,
                        "notes": {"invoice_id": str(invoice_id)},
                    },
                )
                response.raise_for_status()
                order = response.json()
            order_id = order["id"]
            if (
                not isinstance(order_id, str)
                or not order_id
                or type(order.get("amount")) is not int
                or order["amount"] != amount_minor
                or order.get("currency") != currency
            ):
                raise PaymentProviderError("Razorpay returned invalid or mismatched order details.")
            return order_id
        except httpx.HTTPStatusError as exc:
            raise PaymentProviderError("Razorpay could not create a checkout order.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            raise PaymentProviderError("Could not create a Razorpay checkout order.") from exc

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=httpx.Timeout(15.0, connect=5.0),
            ) as client:
                response = await client.get(f"{self.api_base_url}/payments/{payment_id}")
                response.raise_for_status()
                payment = response.json()
            if not isinstance(payment, dict):
                raise PaymentProviderError("Razorpay returned an invalid payment response.")
            return payment
        except httpx.HTTPStatusError as exc:
            raise PaymentProviderError("Razorpay could not confirm the payment.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError) as exc:
            raise PaymentProviderError("Could not confirm payment with Razorpay.") from exc
