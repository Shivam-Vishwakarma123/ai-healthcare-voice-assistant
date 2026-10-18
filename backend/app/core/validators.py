"""Shared field validators and input normalizers."""

from __future__ import annotations


def strip_full_name(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) < 2:
        raise ValueError("Full name must contain at least 2 non-space characters.")
    return cleaned


def validate_strong_password(value: str) -> str:
    if (
        not any(char.islower() for char in value)
        or not any(char.isupper() for char in value)
        or not any(char.isdigit() for char in value)
        or not any(not char.isalnum() for char in value)
    ):
        raise ValueError("Password must include lowercase, uppercase, numeric, and special characters.")
    return value


def validate_password_confirmation(password: str | None, confirmation: str) -> str:
    if password is not None and confirmation != password:
        raise ValueError("Password confirmation does not match.")
    return confirmation
