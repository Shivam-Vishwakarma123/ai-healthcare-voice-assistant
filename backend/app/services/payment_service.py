import logging
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


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

    async def capture_payment(self, *, payment_id: str, amount_minor: int, currency: str) -> dict[str, Any]: ...

    async def create_refund(self, *, payment_id: str, amount_minor: int, reason: str) -> dict[str, Any]: ...


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
                        "payment_capture": 1,
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
            logger.warning("Razorpay order API rejected request (status=%s).", exc.response.status_code)
            raise PaymentProviderError("Razorpay could not create a checkout order.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Razorpay order request failed (kind=%s).", type(exc).__name__)
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
            logger.warning("Razorpay payment lookup failed (status=%s).", exc.response.status_code)
            raise PaymentProviderError("Razorpay could not confirm the payment.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Razorpay payment lookup failed (kind=%s).", type(exc).__name__)
            raise PaymentProviderError("Could not confirm payment with Razorpay.") from exc

    async def capture_payment(self, *, payment_id: str, amount_minor: int, currency: str = "INR") -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=httpx.Timeout(15.0, connect=5.0),
            ) as client:
                response = await client.post(
                    f"{self.api_base_url}/payments/{payment_id}/capture",
                    json={"amount": amount_minor, "currency": currency},
                )
                response.raise_for_status()
                payment = response.json()
            if not isinstance(payment, dict):
                raise PaymentProviderError("Razorpay returned an invalid capture response.")
            return payment
        except httpx.HTTPStatusError as exc:
            logger.warning("Razorpay payment capture failed (status=%s).", exc.response.status_code)
            raise PaymentProviderError("Razorpay could not capture the payment.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Razorpay payment capture failed (kind=%s).", type(exc).__name__)
            raise PaymentProviderError("Could not capture payment with Razorpay.") from exc

    async def create_refund(self, *, payment_id: str, amount_minor: int, reason: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=httpx.Timeout(15.0, connect=5.0),
            ) as client:
                response = await client.post(
                    f"{self.api_base_url}/payments/{payment_id}/refund",
                    json={"amount": amount_minor, "notes": {"reason": reason[:200]}},
                )
                response.raise_for_status()
                refund = response.json()
            if (
                not isinstance(refund, dict)
                or not isinstance(refund.get("id"), str)
                or refund.get("payment_id") != payment_id
                or type(refund.get("amount")) is not int
                or refund.get("amount") != amount_minor
            ):
                raise PaymentProviderError("Razorpay returned invalid or mismatched refund details.")
            return refund
        except httpx.HTTPStatusError as exc:
            raise PaymentProviderError("Razorpay could not create the refund.") from exc
        except PaymentProviderError:
            raise
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            raise PaymentProviderError("Could not create a Razorpay refund.") from exc
