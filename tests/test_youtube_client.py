import unittest
from unittest.mock import MagicMock, patch
from src.youtube_client import YouTubeClient

class TestYouTubeClient(unittest.TestCase):
    def setUp(self):
        with patch("src.youtube_client.build") as mock_build:
            self.mock_youtube = MagicMock()
            mock_build.return_value = self.mock_youtube
            self.client = YouTubeClient(api_key="dummy_api_key")

    def test_fetch_videos_statistics_with_retry_chunking(self):
        """60件のIDを渡したときに25件ずつチャンク分割されてリクエストされること"""
        video_ids = [f"vid_{i}" for i in range(60)]

        # mock response helper
        def mock_videos_list(part, id):
            mock_req = MagicMock()
            ids = id.split(",")
            items = [{"id": vid, "statistics": {"viewCount": "100", "likeCount": "10"}} for vid in ids]
            mock_req.execute.return_value = {"items": items}
            return mock_req

        self.client.youtube.videos().list.side_effect = mock_videos_list

        stats = self.client._fetch_videos_statistics_with_retry(video_ids, chunk_size=25, max_retries=2)

        self.assertEqual(len(stats), 60)
        # 25, 25, 10 の 3 回呼ばれる
        self.assertEqual(self.client.youtube.videos().list.call_count, 3)
        self.assertEqual(stats["vid_0"]["views"], 100)
        self.assertEqual(stats["vid_0"]["likes"], 10)

    @patch("time.sleep", return_value=None)
    def test_fetch_videos_statistics_silent_drop_and_retry_success(self, mock_sleep):
        """1回目で一部IDがサイレント脱落しても、自動リトライで取得できること"""
        video_ids = ["vid_1", "vid_2", "vid_3"]

        call_count = 0
        def mock_videos_list(part, id):
            nonlocal call_count
            call_count += 1
            mock_req = MagicMock()
            ids = id.split(",")
            if call_count == 1:
                # 1回目は vid_2 が脱落
                items = [
                    {"id": "vid_1", "statistics": {"viewCount": "10", "likeCount": "1"}},
                    {"id": "vid_3", "statistics": {"viewCount": "30", "likeCount": "3"}},
                ]
            else:
                # 2回目のリトライで vid_2 が返る
                self.assertEqual(ids, ["vid_2"])
                items = [
                    {"id": "vid_2", "statistics": {"viewCount": "20", "likeCount": "2"}}
                ]
            mock_req.execute.return_value = {"items": items}
            return mock_req

        self.client.youtube.videos().list.side_effect = mock_videos_list

        stats = self.client._fetch_videos_statistics_with_retry(video_ids, chunk_size=25, max_retries=2)

        self.assertEqual(len(stats), 3)
        self.assertEqual(stats["vid_1"]["likes"], 1)
        self.assertEqual(stats["vid_2"]["likes"], 2)
        self.assertEqual(stats["vid_3"]["likes"], 3)
        self.assertEqual(call_count, 2)
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    def test_fetch_videos_statistics_retry_failure_returns_none(self, mock_sleep):
        """リトライ上限を超えても返ってこないIDは views=None, likes=None を返すこと"""
        video_ids = ["vid_1", "vid_2"]

        # 常に vid_1 しか返さない
        def mock_videos_list(part, id):
            mock_req = MagicMock()
            items = [{"id": "vid_1", "statistics": {"viewCount": "10", "likeCount": "1"}}]
            mock_req.execute.return_value = {"items": items}
            return mock_req

        self.client.youtube.videos().list.side_effect = mock_videos_list

        stats = self.client._fetch_videos_statistics_with_retry(video_ids, chunk_size=25, max_retries=2)

        self.assertEqual(stats["vid_1"]["likes"], 1)
        self.assertIsNone(stats["vid_2"]["likes"])
        self.assertIsNone(stats["vid_2"]["views"])

    def test_get_total_likes_safeguard(self):
        """likes が None の動画があっても TypeError にならず合計できること"""
        self.client.get_all_videos_stats = MagicMock(return_value=[
            {"video_id": "v1", "likes": 10},
            {"video_id": "v2", "likes": None},
            {"video_id": "v3", "likes": 5},
        ])

        total = self.client.get_total_likes("channel_id")
        self.assertEqual(total, 15)

if __name__ == "__main__":
    unittest.main()
