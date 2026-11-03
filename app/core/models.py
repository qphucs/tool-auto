import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Mọi thời gian trong DB đều là UTC (không kèm múi giờ)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enum(cls):
    # Lưu giá trị ("youtube") thay vì tên ("YOUTUBE") để DB dễ đọc
    return Enum(cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


class Platform(str, enum.Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


PLATFORM_LABELS = {
    Platform.YOUTUBE: "YouTube",
    Platform.TIKTOK: "TikTok",
    Platform.FACEBOOK: "Facebook Fanpage",
    Platform.INSTAGRAM: "Instagram",
}


class AccountStatus(str, enum.Enum):
    NEEDS_LOGIN = "needs_login"
    ACTIVE = "active"
    EXPIRED = "expired"
    ERROR = "error"


ACCOUNT_STATUS_LABELS = {
    AccountStatus.NEEDS_LOGIN: "Chưa đăng nhập",
    AccountStatus.ACTIVE: "Đang hoạt động",
    AccountStatus.EXPIRED: "Hết phiên đăng nhập",
    AccountStatus.ERROR: "Lỗi khi kiểm tra",
}


class TargetStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    POSTING = "posting"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


TARGET_STATUS_LABELS = {
    TargetStatus.DRAFT: "Nháp",
    TargetStatus.PENDING_REVIEW: "Chờ duyệt",
    TargetStatus.REJECTED: "Đã từ chối",
    TargetStatus.SCHEDULED: "Đã lên lịch",
    TargetStatus.POSTING: "Đang đăng",
    TargetStatus.SUCCESS: "Thành công",
    TargetStatus.FAILED: "Lỗi",
    TargetStatus.NEEDS_ATTENTION: "Cần bạn xử lý",
}


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column(_enum(Platform))
    name: Mapped[str] = mapped_column(String(200))
    group_name: Mapped[str] = mapped_column(String(100), default="")
    profile_dir: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[AccountStatus] = mapped_column(_enum(AccountStatus), default=AccountStatus.NEEDS_LOGIN)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    targets: Mapped[list["PostTarget"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class StyleTemplate(Base):
    """Mẫu phong cách phân tích từ video mẫu; chi tiết lưu dạng JSON trong spec_json."""

    __tablename__ = "style_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_video: Mapped[str] = mapped_column(String(500), default="")
    spec_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_path: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(300), default="")
    duration_sec: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("style_templates.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    posts: Mapped[list["Post"]] = relationship(back_populates="video")


class Post(Base):
    """Một video kèm nhiều đích đăng (mỗi đích là một tài khoản)."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    video: Mapped[Video] = relationship(back_populates="posts")
    targets: Mapped[list["PostTarget"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class PostTarget(Base):
    """Một lần đăng: video X lên tài khoản Y, có nội dung và trạng thái riêng."""

    __tablename__ = "post_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[TargetStatus] = mapped_column(_enum(TargetStatus), default=TargetStatus.DRAFT)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    result_url: Mapped[str] = mapped_column(String(500), default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    post: Mapped[Post] = relationship(back_populates="targets")
    account: Mapped[Account] = relationship(back_populates="targets")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("post_targets.id", ondelete="SET NULL"))
