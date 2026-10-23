from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status

from app.core.config import settings

_attempts: OrderedDict[str, deque[float]] = OrderedDict()
_lock = Lock()
_MAX_BUCKETS = 10_000


# Enforces sliding-window rate limits by IP address and user identity to prevent brute-force attacks.
def enforce_auth_rate_limit(request: Request, identity: str) -> None:
    now = monotonic()
    window = settings.auth_rate_limit_window_seconds
    limit = settings.auth_rate_limit_attempts
    address = request.client.host if request.client else "unknown"
    path = request.url.path
    keys = (
        f"{path}:ip:{address}",
        f"{path}:identity:{identity.casefold()[:254]}",
    )
    with _lock:
        attempt_windows = [_attempts.setdefault(key, deque()) for key in keys]
        for attempts in attempt_windows:
            while attempts and now - attempts[0] >= window:
                attempts.popleft()
        blocked = [attempts for attempts in attempt_windows if len(attempts) >= limit]
        if blocked:
            retry_after = max(max(1, int(window - (now - attempts[0]))) for attempts in blocked)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many authentication attempts. Please wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )
        for attempts in attempt_windows:
            attempts.append(now)
        for key in keys:
            _attempts.move_to_end(key)
        while len(_attempts) > _MAX_BUCKETS:
            _attempts.popitem(last=False)


# Clears all in-memory rate-limiting buckets, primarily used in test teardowns.
def reset_auth_rate_limits() -> None:
    with _lock:
        _attempts.clear()
