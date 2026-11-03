import unittest
from unittest.mock import MagicMock, patch
from src.slack_client import SlackClient

class TestSlackClient(unittest.TestCase):
    def setUp(self):
        self.slack = SlackClient(webhook_url="http://dummy")

    def test_subscriber_diff_block_increase(self):
        """登録者増加ブロックのフォーマット（2日遅延情報、直リンク、反映分、人、累計 X人）"""
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
        # 直リンク化、反映分、人、累計 X人（+なし）の検証
        self.assertIn("• 🎬 *<https://youtu.be/vid1|【作業が一気に終わる】ピアノ＆雨音>*: 反映分 *+2人* (累計 3人)", text)

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
        self.assertIn("• 🆕 *<https://youtu.be/vid2|自然音動画>*: 反映分 *-1人* (累計 5人)", text)

    def test_like_diff_block_regression(self):
        """いいね数増減ブロックが直リンク化され、前日比・計のフォーマットを維持していること"""
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
        self.assertIn("• 🎬 *<https://youtu.be/vid3|リラックスBGM>*: 前日比 *+1* (計7)", text)

    def test_video_diff_block_with_published_at_and_jst_conversion(self):
        """published_at がある場合、JST に正確に変換されて (MM/DD) が付記されること"""
        # UTC 2026-10-04T22:30:00Z は JST 2026-10-05T07:30:00 なので (10/05) になるべき
        videos = [
            {
                "video_id": "vid_morning",
                "title": "朝のピアノBGM",
                "diff": 3,
                "current_likes": 10,
                "published_at": "2026-10-04T22:30:00Z",
                "is_new": True
            }
        ]
        block = self.slack._build_like_diff_block(
            "👍 いいね数が増加した動画",
            videos,
            is_increase=True
        )
        self.assertIsNotNone(block)
        text = block["text"]["text"]
        self.assertIn("• 🆕 *<https://youtu.be/vid_morning|朝のピアノBGM>* (10/05): 前日比 *+3* (計10)", text)

    def test_video_diff_block_special_characters_escaped(self):
        """タイトルに &, <, > が含まれていてもリンク構文が壊れずエスケープされること"""
        videos = [
            {
                "video_id": "vid_special",
                "title": "【集中】Rain & <Storm> ピアノ",
                "diff": 1,
                "current_likes": 5,
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
        self.assertIn("• 🎬 *<https://youtu.be/vid_special|【集中】Rain &amp; &lt;Storm&gt; ピアノ>*: 前日比 *+1* (計5)", text)

    def test_video_diff_block_without_video_id_and_published_at_fallback(self):
        """video_id や published_at が存在しない場合はプレーンテキストとして安全にフォールバックすること"""
        videos = [
            {
                "title": "通常動画",
                "diff": 1,
                "current_likes": 3,
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
        self.assertIn("• 🎬 *通常動画*: 前日比 *+1* (計3)", text)

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

    def test_recent_video_attachments_thumbnails_and_links(self):
        """スレッド側アタッチメントに thumb_url と title_link が正しく付与されること"""
        recent_kpis = [
            {
                "video_id": "vid_thread_1",
                "title": "秋の夜長ピアノ",
                "published_at": "2026-10-10T12:00:00Z",
                "metrics": {
                    "views": 500,
                    "likes": 20,
                    "diff": {}
                }
            },
            {
                # video_id がない場合のフォールバック検証
                "title": "IDなし動画",
                "published_at": "2026-10-10T12:00:00Z",
                "metrics": {
                    "views": 100,
                    "likes": 2,
                    "diff": {}
                }
            }
        ]
        attachments = self.slack._build_recent_video_attachments(recent_kpis)
        self.assertEqual(len(attachments), 3) # 2動画 + 1フッター

        att1 = attachments[0]
        self.assertEqual(att1["title_link"], "https://youtu.be/vid_thread_1")
        self.assertEqual(att1["thumb_url"], "https://i.ytimg.com/vi/vid_thread_1/mqdefault.jpg")

        att2 = attachments[1]
        self.assertNotIn("title_link", att2)
        self.assertNotIn("thumb_url", att2)

    def test_send_kpi_alert_blocks(self):
        """send_kpi_alert 全体で生成される blocks のヘッダー・遅延情報・注記の検証"""
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
            # 反映分・単位・累計・直リンクの存在確認
            self.assertTrue(any("反映分 *+2人* (累計 3人)" in t for t in block_texts))
            self.assertTrue(any("<https://youtu.be/v1|雨音ピアノ>" in t for t in block_texts))

            # context 注記ブロックの存在確認
            context_blocks = [b for b in blocks if b.get("type") == "context"]
            self.assertTrue(len(context_blocks) > 0)
            context_texts = [el.get("text", "") for el in context_blocks[0].get("elements", [])]
            self.assertTrue(any("YouTubeの仕様上、約2〜3日遅れてAPI確定・反映されます" in t for t in context_texts))
            # recent_videos_kpis が未指定のため、スレッド誘導文は含まれない
            self.assertFalse(any("スレッドに投稿されています" in t for t in context_texts))

    def test_send_kpi_alert_with_recent_videos_kpis_shows_thread_guide(self):
        """recent_videos_kpis がある場合はスレッド誘導文が表示されること"""
        current_kpi = {"channel_title": "Ch", "subscriber_count": 40, "view_count": 16000, "total_like_count": 227}
        recent_kpis = [{"video_id": "v1", "title": "Vid 1"}]

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "ts": "12345.678"}
            mock_post.return_value = mock_resp
            self.slack.bot_token = "xoxb-dummy"
            self.slack.channel = "C12345"

            self.slack.send_kpi_alert(current_kpi=current_kpi, recent_videos_kpis=recent_kpis)
            payload = mock_post.call_args[1]["json"]
            blocks = payload["blocks"]
            context_blocks = [b for b in blocks if b.get("type") == "context"]
            self.assertEqual(len(context_blocks), 1)
            context_texts = [el.get("text", "") for el in context_blocks[0].get("elements", [])]
            self.assertTrue(any("スレッドに投稿されています" in t for t in context_texts))

    def test_send_kpi_alert_without_any_context_elements_does_not_create_empty_context_block(self):
        """recent_videos_kpis も登録者増減もない場合、不正な空 context ブロックが生成されないこと"""
        current_kpi = {"channel_title": "Ch", "subscriber_count": 40, "view_count": 16000, "total_like_count": 227}

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "ts": "12345.678"}
            mock_post.return_value = mock_resp
            self.slack.bot_token = "xoxb-dummy"
            self.slack.channel = "C12345"

            self.slack.send_kpi_alert(current_kpi=current_kpi)
            payload = mock_post.call_args[1]["json"]
            blocks = payload["blocks"]
            context_blocks = [b for b in blocks if b.get("type") == "context"]
            self.assertEqual(len(context_blocks), 0)

    def test_send_weekly_report_cvr(self):
        """send_weekly_report で親メッセージの fields に CVR (登録転換率) が正しく含まれること"""
        summary_data = {
            "channel_title": "テストチャンネル",
            "start_date": "2026-10-26",
            "end_date": "2026-11-01",
            "subscriber_growth": 5,
            "view_growth": 1000,
            "like_growth": 20,
            "current_subscribers": 50,
            "cvr": 0.50
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "ts": "12345.678"}
            mock_post.return_value = mock_resp
            self.slack.bot_token = "xoxb-dummy"
            self.slack.channel = "C12345"

            self.slack.send_weekly_report(
                summary_data=summary_data,
                advice_text="アドバイステキスト"
            )
            # 親メッセージ（1回目のAPI呼び出し）の payload を取得
            payload = mock_post.call_args_list[0][1]["json"]
            blocks = payload["blocks"]

            # fields を探す
            fields_block = [b for b in blocks if b.get("type") == "section" and "fields" in b]
            self.assertEqual(len(fields_block), 1)
            field_texts = [f["text"] for f in fields_block[0]["fields"]]
            self.assertEqual(len(field_texts), 4) # 4項目グリッド

            # CVR 項目の検証
            cvr_field = [t for t in field_texts if "*🎯 CVR (登録転換率)*" in t]
            self.assertEqual(len(cvr_field), 1)
            self.assertIn("0.50%", cvr_field[0])
            self.assertIn("_(登録増 / 再生数増)_", cvr_field[0])

    def test_send_weekly_report_cvr_zero_views_and_net_loss(self):
        """ゼロ除算時および登録者純減時の CVR 表示検証"""
        # 1. ゼロ除算ケース
        summary_zero = {
            "channel_title": "Ch",
            "start_date": "2026-10-26",
            "end_date": "2026-11-01",
            "subscriber_growth": 0,
            "view_growth": 0,
            "like_growth": 0,
            "current_subscribers": 50
        }
        # 2. 純減ケース
        summary_loss = {
            "channel_title": "Ch",
            "start_date": "2026-10-26",
            "end_date": "2026-11-01",
            "subscriber_growth": -2,
            "view_growth": 1000,
            "like_growth": 10,
            "current_subscribers": 48
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "ts": "12345.678"}
            mock_post.return_value = mock_resp
            self.slack.bot_token = "xoxb-dummy"
            self.slack.channel = "C12345"

            # ゼロ除算テスト
            self.slack.send_weekly_report(summary_data=summary_zero, advice_text="advice")
            payload_zero = mock_post.call_args_list[0][1]["json"]
            fields_block_zero = [b for b in payload_zero["blocks"] if b.get("type") == "section" and "fields" in b][0]
            field_texts_zero = [f["text"] for f in fields_block_zero["fields"]]
            cvr_field_zero = [t for t in field_texts_zero if "*🎯 CVR (登録転換率)*" in t][0]
            self.assertIn("0.00%", cvr_field_zero)

            # 純減テスト
            mock_post.reset_mock()
            self.slack.send_weekly_report(summary_data=summary_loss, advice_text="advice")
            payload_loss = mock_post.call_args_list[0][1]["json"]
            fields_block_loss = [b for b in payload_loss["blocks"] if b.get("type") == "section" and "fields" in b][0]
            field_texts_loss = [f["text"] for f in fields_block_loss["fields"]]
            cvr_field_loss = [t for t in field_texts_loss if "*🎯 CVR (登録転換率)*" in t][0]
            self.assertIn("-0.20%", cvr_field_loss)
            self.assertIn("(※純減)", cvr_field_loss)

if __name__ == "__main__":
    unittest.main()
