from app.core.models import Platform
from app.uploaders.base import Uploader
from app.uploaders.youtube import YouTubeUploader

# Nền tảng nào có trong đây thì mới chọn được để đăng
UPLOADERS: dict[Platform, Uploader] = {
    Platform.YOUTUBE: YouTubeUploader(),
}


def get_uploader(platform: Platform) -> Uploader | None:
    return UPLOADERS.get(platform)
