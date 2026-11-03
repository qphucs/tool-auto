"""DB lưu giờ UTC; giao diện hiện giờ địa phương."""

from datetime import datetime, timezone


def local_to_utc(local_naive: datetime) -> datetime:
    return local_naive.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(utc_naive: datetime) -> datetime:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def fmt_local(utc_naive: datetime | None) -> str:
    return utc_to_local(utc_naive).strftime("%d/%m/%Y %H:%M") if utc_naive else ""
