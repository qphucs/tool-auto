"""Lưu thông tin nhạy cảm (API key) trong Windows Credential Manager thay vì file JSON."""

import logging

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "ToolAuto"


def get_secret(name: str) -> str:
    try:
        return keyring.get_password(SERVICE, name) or ""
    except KeyringError:
        log.exception("Không đọc được secret %s", name)
        return ""


def set_secret(name: str, value: str) -> None:
    if value:
        keyring.set_password(SERVICE, name, value)
        return
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass


def ai_key_name(provider: str) -> str:
    return f"ai.{provider}.api_key"
