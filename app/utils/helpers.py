from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def slugify(text: str) -> str:
    return text.lower().strip().replace(" ", "-")
