import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Mọi thời gian trong DB đều là UTC (không kèm múi giờ)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enum(cls):
    # Lưu giá trị ("ready") thay vì tên ("READY") để DB dễ đọc
    return Enum(cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


class ProjectStatus(str, enum.Enum):
    NEW = "new"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


PROJECT_STATUS_LABELS = {
    ProjectStatus.NEW: "Chưa phân tích",
    ProjectStatus.ANALYZING: "Đang phân tích",
    ProjectStatus.READY: "Đã có kịch bản",
    ProjectStatus.FAILED: "Lỗi",
}


class ClipStatus(str, enum.Enum):
    SCRIPT = "script"  # chờ duyệt kịch bản
    DRAFT = "draft"  # đã có nháp, chờ xem
    FINAL = "final"  # đã có bản cuối
    FAILED = "failed"
    SKIPPED = "skipped"


CLIP_STATUS_LABELS = {
    ClipStatus.SCRIPT: "Chờ duyệt kịch bản",
    ClipStatus.DRAFT: "Đã có nháp",
    ClipStatus.FINAL: "Đã xong",
    ClipStatus.FAILED: "Lỗi",
    ClipStatus.SKIPPED: "Đã bỏ",
}


class Project(Base):
    """Một video gốc."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    source_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus), default=ProjectStatus.NEW)
    language: Mapped[str] = mapped_column(String(10), default="")
    duration: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    clips: Mapped[list["Clip"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Clip.position"
    )


class Clip(Base):
    """Một video ngắn làm từ video gốc."""

    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[ClipStatus] = mapped_column(_enum(ClipStatus), default=ClipStatus.SCRIPT)
    script_json: Mapped[str] = mapped_column(Text, default="{}")
    draft_path: Mapped[str] = mapped_column(String(500), default="")
    final_path: Mapped[str] = mapped_column(String(500), default="")
    music_path: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="clips")
