from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import MomentLog, Room


@dataclass(frozen=True)
class LogPostPermission:
    allowed: bool
    reason: str
    message: str


def room_is_active(room: Room, now=None) -> bool:
    """開催中Roomかどうかを、全画面で共通に判定する。"""
    now = now or timezone.now()
    return not room.is_archived and room.starts_at <= now < room.ends_at


def require_active_room(room: Room, now=None) -> None:
    """Roomを変更する操作の入口で、開催中以外を拒否する。"""
    if not room_is_active(room, now=now):
        raise PermissionDenied("開催中のRoomだけ変更できます。")


def log_post_permission(
    room: Room,
    entry_type: str = MomentLog.EntryType.MOMENT,
    now=None,
) -> LogPostPermission:
    """SHUNKAN-logを投稿できるかを判定する。

    `moment` は `starts_at` 以降 `ends_at` まで、`reflection` は `ends_at` 以降
    `reflection_deadline_at` までを投稿可能とする。
    """
    now = now or timezone.now()

    if room.is_archived:
        return LogPostPermission(
            allowed=False,
            reason="archived",
            message="アーカイブ済みのRoomには投稿できません。",
        )

    if entry_type == MomentLog.EntryType.REFLECTION:
        if now < room.ends_at:
            return LogPostPermission(
                allowed=False,
                reason="room_not_ended",
                message="振り返りはRoomが終了してから投稿できます。",
            )
        if room.reflection_deadline_at is None:
            return LogPostPermission(
                allowed=False,
                reason="reflection_deadline_unset",
                message="このRoomには振り返りの期限が設定されていません。",
            )
        if now > room.reflection_deadline_at:
            return LogPostPermission(
                allowed=False,
                reason="reflection_closed",
                message="振り返りの期限が過ぎました。",
            )
        return LogPostPermission(
            allowed=True,
            reason="reflection_open",
            message="振り返りを投稿できます。",
        )

    if now < room.starts_at:
        return LogPostPermission(
            allowed=False,
            reason="room_not_started",
            message="Roomが始まる前は投稿できません。",
        )
    if now >= room.ends_at:
        return LogPostPermission(
            allowed=False,
            reason="room_ended",
            message="Roomが終了したため、通常のSHUNKAN-logは投稿できません。",
        )
    return LogPostPermission(
        allowed=True,
        reason="moment_open",
        message="今の瞬間を投稿できます。",
    )
