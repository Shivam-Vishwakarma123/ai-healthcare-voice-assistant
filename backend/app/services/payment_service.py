import asyncio
import logging
import re
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class PaymentProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        provider_http_status: int | None = None,
        provider_code: str | None = None,
        provider_reason: str | None = None,
        provider_field: str | None = None,
        error_phase: str | None = None,
    ):
        super().__init__(message)
        self.provider_http_status = provider_http_status
        self.provider_code = provider_code
        self.provider_reason = provider_reason
        self.provider_field = provider_field
        self.error_phase = error_phase


class PaymentService(Protocol):
    async def create_order(
        self,
        *,
        invoice_id: int,
        receipt: str,
        amount_minor: int,
        currency: str,
        checkout_config_id: str | None = None,
    ) -> str: ...

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...

    async def capture_payment(self, *, payment_id: str, amount_minor: int, currency: str) -> dict[str, Any]: ...

    async def create_refund(self, *, payment_id: str, amount_minor: int, reason: str) -> dict[str, Any]: ...


class RazorpayPaymentService:
    def __init__(self, key_id: str, key_secret: str, api_base_url: str):
        self.key_id = key_id
        self.key_secret = key_secret
        self.api_base_url = api_base_url.rstrip("/")

    @property
    def is_test_mode(self) -> bool:
        return bool(self.key_id and self.key_id.startswith("rzp_test_"))

    async def create_order(
        self,
        *,
        invoice_id: int,
        receipt: str,
        amount_minor: int,
        currency: str,
        checkout_config_id: str | None = None,
    ) -> str:
        if type(amount_minor) is not int or amount_minor < 100:
            raise ValueError("Razorpay orders require an amount of at least 100 paise.")
        if not isinstance(receipt, str) or not receipt or len(receipt) > 40 or not receipt.isascii():
            raise ValueError("Razorpay order receipts must be non-empty ASCII strings of at most 40 characters.")

        order_data = {
            "amount": amount_minor,
            "currency": currency,
            "receipt": receipt,
            "notes": {"invoice_id": str(invoice_id)},
        }
        if checkout_config_id:
            order_data["checkout_config_id"] = checkout_config_id

        response = None
        try:
            async with httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=httpx.Timeout(20.0, connect=10.0),
            ) as client:
                for attempt in range(3):
                    try:
                        response = await client.post(
                            f"{self.api_base_url}/orders",
                            json=order_data,
                        )
                        break
                    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                        if attempt < 2:
                            logger.info(
                                "Retrying Razorpay order request after transient connection error (attempt %s/3): %s (is_test_mode=%s)",
                                attempt + 1,
                                type(exc).__name__,
                                self.is_test_mode,
                            )
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise
        except httpx.RequestError as exc:
            logger.warning(
                "Razorpay order failed during network communication (kind=%s, is_test_mode=%s)",
                type(exc).__name__,
                self.is_test_mode,
                exc_info=True,
            )
            raise PaymentProviderError(
                "Could not create a Razorpay checkout order.",
                error_phase="network_communication",
            ) from exc

        if response is None:
            raise PaymentProviderError(
                "Could not create a Razorpay checkout order.",
                error_phase="network_communication",
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            diagnostic: dict[str, Any] = {"http_status": exc.response.status_code}
            try:
                provider_error = exc.response.json().get("error", {})
                if isinstance(provider_error, dict):
                    for field in ("code", "reason", "field", "description"):
                        value = provider_error.get(field)
                        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.\s-]{1,120}", value):
                            diagnostic[field] = value
            except (ValueError, AttributeError):
                pass
            logger.warning(
                "Razorpay order API rejected request (http_status=%s, code=%s, reason=%s, field=%s, is_test_mode=%s)",
                diagnostic.get("http_status"),
                diagnostic.get("code"),
                diagnostic.get("reason"),
                diagnostic.get("field"),
                self.is_test_mode,
            )
            raise PaymentProviderError(
                "Razorpay could not create a checkout order.",
                provider_http_status=diagnostic["http_status"],
                provider_code=diagnostic.get("code"),
                provider_reason=diagnostic.get("reason") or diagnostic.get("description"),
                provider_field=diagnostic.get("field"),
                error_phase="provider_rejection",
            ) from exc

        try:
            order = response.json()
            order_id = order["id"]
            if (
                not isinstance(order_id, str)
                or not order_id
                or type(order.get("amount")) is not int
                or order["amount"] != amount_minor
                or order.get("currency") != currency
            ):
                raise PaymentProviderError(
                    "Razorpay returned invalid or mismatched order details.",
                    error_phase="response_handling",
                )
            return order_id
        except PaymentProviderError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Razorpay order response parsing failed: %s", exc)
            raise PaymentProviderError(
                "Could not process Razorpay checkout order response.",
                error_phase="response_handling",
            ) from exc

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
