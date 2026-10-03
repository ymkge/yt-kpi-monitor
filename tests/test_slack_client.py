import unittest
from src.slack_client import SlackClient

class TestSlackClient(unittest.TestCase):
    def setUp(self):
        self.slack = SlackClient(webhook_url="http://dummy")

    def test_subscriber_diff_block_increase(self):
        """登録者増加ブロックのフォーマット（2日遅延情報、反映分、人、累計 X人）"""
        videos = [
            {
                "video_id": "vid1",
                "title": "【作業が一気に終わる】ピアノ＆雨音",
                "diff": 2,
                "current_subscribers": 3,
                "is_new": False
            }
        ]
        block = self.slack._build_subscriber_diff_block(
            "👥 登録者が増加した動画 (2日遅延情報)",
            videos,
            is_increase=True
        )
        self.assertIsNotNone(block)
        text = block["text"]["text"]
        
        # ヘッダー検証
        self.assertIn("*👥 登録者が増加した動画 (2日遅延情報)*", text)
        # 反映分、人、累計 X人（+なし）の検証
        self.assertIn("• 🎬 *【作業が一気に終わる】ピアノ＆雨音*: 反映分 *+2人* (累計 3人)", text)

    def test_subscriber_diff_block_decrease(self):
        """登録者減少（補正）ブロックのフォーマット"""
        videos = [
            {
                "video_id": "vid2",
                "title": "自然音動画",
                "diff": -1,
                "current_subscribers": 5,
                "is_new": True
            }
        ]
        block = self.slack._build_subscriber_diff_block(
            "👤 登録者が減少（補正）した動画 (2日遅延情報)",
            videos,
            is_increase=False
        )
        self.assertIsNotNone(block)
        text = block["text"]["text"]
        
        self.assertIn("*👤 登録者が減少（補正）した動画 (2日遅延情報)*", text)
        self.assertIn("• 🆕 *自然音動画*: 反映分 *-1人* (累計 5人)", text)

    def test_like_diff_block_regression(self):
        """いいね数増減ブロックが既存のフォーマット（前日比、計、単位なし）を維持していること"""
        videos = [
            {
                "video_id": "vid3",
                "title": "リラックスBGM",
                "diff": 1,
                "current_likes": 7,
                "is_new": False
            }
        ]
        block = self.slack._build_like_diff_block(
            "👍 いいね数が増加した動画",
            videos,
            is_increase=True
        )
        self.assertIsNotNone(block)
        text = block["text"]["text"]
        
        self.assertIn("*👍 いいね数が増加した動画*", text)
        # 既存の仕様: "前日比 *+1* (計7)"
        self.assertIn("• 🎬 *リラックスBGM*: 前日比 *+1* (計7)", text)

    def test_max_display_overflow(self):
        """上限(3件)を超えた場合の省略メッセージ"""
        videos = [
            {"video_id": f"v{i}", "title": f"動画{i}", "diff": 5 - i, "current_subscribers": 10, "is_new": False}
            for i in range(5)
        ]
        block = self.slack._build_subscriber_diff_block(
            "👥 登録者が増加した動画 (2日遅延情報)",
            videos,
            is_increase=True,
            max_display=3
        )
        self.assertIsNotNone(block)
        text = block["text"]["text"]
        
        self.assertIn("_...他 2 件の動画で登録者が増加_", text)

    def test_send_kpi_alert_blocks(self):
        """send_kpi_alert 全体で生成される blocks のヘッダー・遅延情報・注記の検証"""
        from unittest.mock import patch, MagicMock

        current_kpi = {
            "channel_title": "テストチャンネル",
            "subscriber_count": 40,
            "view_count": 16000,
            "total_like_count": 227
        }
        previous_kpi = {
            "subscriber_count": 39,
            "view_count": 15800,
            "total_like_count": 224
        }
        increased_sub = [
            {"video_id": "v1", "title": "雨音ピアノ", "diff": 2, "current_subscribers": 3, "is_new": False}
        ]

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "ts": "12345.678"}
            mock_post.return_value = mock_resp

            # bot_token と channel をセットして Bot 送信
            self.slack.bot_token = "xoxb-dummy"
            self.slack.channel = "C12345"

            ts = self.slack.send_kpi_alert(
                current_kpi=current_kpi,
                previous_kpi=previous_kpi,
                increased_subscriber_videos=increased_sub
            )
            self.assertEqual(ts, "12345.678")

            # 呼び出し時の payload blocks を検証
            payload = mock_post.call_args[1]["json"]
            blocks = payload["blocks"]

            block_texts = [b.get("text", {}).get("text", "") for b in blocks if "text" in b]
            
            # 遅延情報付きヘッダーの存在確認
            self.assertTrue(any("👥 登録者が増加した動画 (2日遅延情報)" in t for t in block_texts))
            # 反映分・単位・累計の存在確認
            self.assertTrue(any("反映分 *+2人* (累計 3人)" in t for t in block_texts))

            # context 注記ブロックの存在確認
            context_blocks = [b for b in blocks if b.get("type") == "context"]
            self.assertTrue(len(context_blocks) > 0)
            context_texts = [el.get("text", "") for el in context_blocks[0].get("elements", [])]
            self.assertTrue(any("YouTubeの仕様上、約2〜3日遅れてAPI確定・反映されます" in t for t in context_texts))

if __name__ == "__main__":
    unittest.main()
