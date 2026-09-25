"""APNs push notifications. Logs instead of sending when APNs isn't configured."""

import logging

from sqlalchemy import select

from pepper import db
from pepper.config import get_settings
from pepper.models import Device

log = logging.getLogger("pepper.push")

_client = None


def _apns():
    global _client
    settings = get_settings()
    if not (settings.apns_key_path and settings.apns_key_id and settings.apns_team_id):
        return None
    if _client is None:
        from aioapns import APNs

        _client = APNs(
            key=settings.apns_key_path,
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=settings.apns_bundle_id,
            use_sandbox=settings.apns_sandbox,
        )
    return _client


async def notify(title: str, body: str, data: dict | None = None, *, category: str | None = None,
                 time_sensitive: bool = False) -> int:
    """Send to every active device with an APNs token. Returns the number of devices targeted."""
    async with db.sessionmaker()() as session:
        tokens = (await session.scalars(
            select(Device.apns_token).where(Device.revoked.is_(False), Device.apns_token.is_not(None))
        )).all()
    client = _apns()
    if client is None or not tokens:
        log.info("push (not sent): %s: %s", title, body)
        return 0

    from aioapns import NotificationRequest, PushType

    aps: dict = {"alert": {"title": title, "body": body}, "sound": "default"}
    if category:
        aps["category"] = category
    if time_sensitive:
        aps["interruption-level"] = "time-sensitive"
    for token in tokens:
        try:
            await client.send_notification(
                NotificationRequest(device_token=token, message={"aps": aps, "data": data or {}}, push_type=PushType.ALERT)
            )
        except Exception:  # one bad token must not stop the rest
            log.exception("push failed for a device")
    return len(tokens)
