import socket
import time

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from youtube_ki_bot.settings import (
    MAX_RESULTS_PER_PAGE,
    SHORTS_MAX_DURATION_SECONDS,
    YOUTUBE_API_MAX_RETRIES,
    YOUTUBE_HTTP_TIMEOUT_SECONDS,
)
from youtube_ki_bot.text_utils import chunked, iso8601_duration_to_seconds


class YouTubeDataService:
    def __init__(self, api_key: str):
        http_client = httplib2.Http(timeout=YOUTUBE_HTTP_TIMEOUT_SECONDS)
        self.youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            http=http_client,
            cache_discovery=False,
        )

    def _execute_request(self, request, description: str):
        for attempt in range(1, YOUTUBE_API_MAX_RETRIES + 1):
            try:
                return request.execute()
            except (socket.timeout, TimeoutError, OSError, HttpError) as exc:
                if attempt == YOUTUBE_API_MAX_RETRIES:
                    raise RuntimeError(
                        f"YouTube-API Anfrage fehlgeschlagen nach "
                        f"{YOUTUBE_API_MAX_RETRIES} Versuchen: {description}"
                    ) from exc
                wait_seconds = attempt * 2
                print(
                    f"Warnung: {description} fehlgeschlagen "
                    f"(Versuch {attempt}/{YOUTUBE_API_MAX_RETRIES}): {exc}. "
                    f"Warte {wait_seconds}s und versuche es erneut."
                )
                time.sleep(wait_seconds)

    def get_uploads_playlist_id(self, channel_id: str) -> str:
        response = self._execute_request(
            self.youtube.channels().list(part="contentDetails", id=channel_id),
            "Kanaldetails laden",
        )
        items = response.get("items", [])
        if not items:
            raise ValueError(f"Kein Kanal für Channel-ID {channel_id} gefunden.")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def get_all_video_ids(self, uploads_playlist_id: str) -> list:
        all_video_ids = []
        next_page_token = None
        page_number = 1
        while True:
            response = self._execute_request(
                self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=MAX_RESULTS_PER_PAGE,
                    pageToken=next_page_token,
                ),
                f"Playlist-Seite {page_number} laden",
            )
            items = response.get("items", [])
            for item in items:
                all_video_ids.append(item["snippet"]["resourceId"]["videoId"])
            print(
                f"Playlist-Seite {page_number}: {len(items)} Videos geladen "
                f"(gesamt: {len(all_video_ids)})"
            )
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
            page_number += 1
        return all_video_ids

    def fetch_video_details(self, video_ids: list) -> list:
        videos = []
        for batch_index, video_id_batch in enumerate(
            chunked(video_ids, MAX_RESULTS_PER_PAGE),
            start=1,
        ):
            response = self._execute_request(
                self.youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(video_id_batch),
                ),
                f"Video-Batch {batch_index} laden",
            )
            batch_items = response.get("items", [])
            print(f"Video-Batch {batch_index}: {len(batch_items)} Detaildatensätze geladen")
            for video in batch_items:
                snippet = video.get("snippet", {})
                statistics = video.get("statistics", {})
                content_details = video.get("contentDetails", {})
                duration_seconds = iso8601_duration_to_seconds(
                    content_details.get("duration", "PT0S")
                )
                videos.append(
                    {
                        "video_id": video["id"],
                        "title": snippet.get("title", ""),
                        "views": int(statistics.get("viewCount", 0)),
                        "likes": int(statistics.get("likeCount", 0)),
                        "comments": int(statistics.get("commentCount", 0)),
                        "duration_seconds": duration_seconds,
                        "published_at": snippet.get("publishedAt", ""),
                        "url": f"https://www.youtube.com/watch?v={video['id']}",
                        "is_short": duration_seconds <= SHORTS_MAX_DURATION_SECONDS,
                    }
                )
        return videos

    @staticmethod
    def filter_and_sort_shorts(videos: list) -> list:
        shorts = [video for video in videos if video["is_short"]]
        shorts.sort(key=lambda video: video["views"], reverse=True)
        return shorts
