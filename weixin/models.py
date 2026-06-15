"""Data structures for Weixin video monitoring."""
from dataclasses import dataclass, field


@dataclass
class OCRItem:
    text: str
    x: int
    y: int
    w: int = 0
    h: int = 0


@dataclass
class Candidate:
    """A candidate video from a search-result page."""
    keyword: str
    hit_text: str
    title_text: str
    author_name: str = ""
    publish_time: str = ""
    like_count: str = ""
    comment_count: str = ""
    share_count: str = ""
    click_x: int = 540
    click_y: int = 800
    score: int = 1
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            import hashlib

            raw = f"weixin|{self.keyword}|{self.author_name}|{self.publish_time}|{self.title_text[:30]}"
            self.fingerprint = hashlib.md5(raw.encode("utf-8")).hexdigest()


@dataclass
class EvidenceRecord:
    """One complete evidence record."""
    platform: str = "weixin"
    search_keyword: str = ""
    capture_time: str = ""
    capture_timestamp: str = ""
    candidate: dict = field(default_factory=dict)

    video_info: dict = field(default_factory=lambda: {
        "blogger_name": "",
        "video_channel_id": "",
        "video_channel_id_raw": "",
        "video_channel_id_needs_review": False,
        "video_channel_id_ambiguous_positions": [],
        "video_link": "",
        "publish_time": "",
        "like_count": "",
        "comment_count": "",
        "share_count": "",
        "raw_ocr": [],
    })
    profile_info: dict = field(default_factory=lambda: {
        "name": "",
        "account": "",
        "subject_type": "",
        "company_full_name": "",
        "raw_ocr": [],
    })
    traffic_info: dict = field(default_factory=lambda: {
        "has_traffic_marker": False,
        "marker_text": "",
        "target_blogger_name": "",
        "target_video_channel_id": "",
        "target_video_channel_id_raw": "",
        "target_video_channel_id_needs_review": False,
        "target_video_channel_id_ambiguous_positions": [],
        "company_full_name": "",
        "company_verified_at": "",
        "raw_ocr": [],
    })
    media_info: dict = field(default_factory=lambda: {
        "full_recording_required": True,
        "recording_video_path": "",
        "recording_audio_path": "",
        "recording_started_at": "",
        "recording_ended_at": "",
        "recording_duration_seconds": 0,
        "has_audio": None,
        "asr_text": "",
        "asr_json_path": "",
    })

    screenshots: list = field(default_factory=list)
    ocr_results: list = field(default_factory=list)

    def to_dict(self):
        return {
            "platform": self.platform,
            "search_keyword": self.search_keyword,
            "capture_time": self.capture_time,
            "capture_timestamp": self.capture_timestamp,
            "candidate": self.candidate,
            "video_info": self.video_info,
            "profile_info": self.profile_info,
            "traffic_info": self.traffic_info,
            "media_info": self.media_info,
            "screenshots": self.screenshots,
        }
