import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import os

from src.main_weekly import main, format_weekly_video_rankings

JST = timezone(timedelta(hours=9))

class TestMainWeekly(unittest.TestCase):
    def test_format_weekly_video_rankings_merging_and_escaping(self):
        """動画ランキングの重複排除、ランクタグ集約、パイプ記号エスケープ、CTR判定の検証"""
        top_views = [
            {"video_id": "v1", "title": "動画A | 完全攻略", "views": 1000, "likes": 50, "impressions": 2000, "ctr": 5.0},
            {"video_id": "v2", "title": "動画B", "views": 800, "likes": 30, "impressions": 500, "ctr": 2.0},
        ]
        top_likes = [
            {"video_id": "v1", "title": "動画A | 完全攻略", "views": 1000, "likes": 50, "impressions": 2000, "ctr": 5.0},
            {"video_id": "v3", "title": "動画C", "views": 300, "likes": 60, "impressions": 0, "ctr": 0.0},
        ]
        top_ctr = [
            {"video_id": "v1", "title": "動画A | 完全攻略", "views": 1000, "likes": 50, "impressions": 2000, "ctr": 5.0},
        ]

        result = format_weekly_video_rankings(
            top_views_videos=top_views,
            top_likes_videos=top_likes,
            top_ctr_videos=top_ctr,
            min_impr=1500
        )

        lines = result.strip().split("\n")
        self.assertEqual(lines[0], "# 動画ランキング (直近28日)")
        self.assertEqual(len(lines), 4) # ヘッダー + 3動画 (v1, v2, v3)

        # v1: 重複マージ、パイプエスケープ、全ランクタグ集約、CTR表示
        v1_line = [l for l in lines if "動画A ｜ 完全攻略" in l][0]
        self.assertIn("再生: 1,000回", v1_line)
        self.assertIn("いいね: 50回", v1_line)
        self.assertIn("CTR: 5.00% (imp: 2,000回)", v1_line)
        self.assertIn("[再生1位]", v1_line)
        self.assertIn("[いいね1位]", v1_line)
        self.assertIn("[CTR1位]", v1_line)

        # v2: インプレッション500 (< 1500) のため CTR: 対象外
        v2_line = [l for l in lines if "動画B" in l][0]
        self.assertIn("CTR: 対象外", v2_line)
        self.assertIn("[再生2位]", v2_line)

        # v3: いいね2位、CTR: 対象外
        v3_line = [l for l in lines if "動画C" in l][0]
        self.assertIn("[いいね2位]", v3_line)
        self.assertIn("CTR: 対象外", v3_line)

    def test_format_weekly_video_rankings_empty(self):
        """動画リストが全て空の場合は空文字列を返すこと"""
        self.assertEqual(format_weekly_video_rankings(), "")
        self.assertEqual(format_weekly_video_rankings([], [], []), "")

    @patch.dict(os.environ, {"YOUTUBE_CHANNEL_ID": "UC_test_channel_id"})
    @patch("src.main_weekly.BigQueryClient")
    @patch("src.main_weekly.GeminiClient")
    @patch("src.main_weekly.SlackClient")
    def test_main_weekly_fetches_summary_with_yesterday_date(
        self, mock_slack_cls, mock_gemini_cls, mock_bq_cls
    ):
        """週次サマリ取得時に、基準日として前日（昨日）の日付文字列が渡されること"""
        mock_bq = MagicMock()
        mock_gemini = MagicMock()
        mock_slack = MagicMock()

        mock_bq_cls.return_value = mock_bq
        mock_gemini_cls.return_value = mock_gemini
        mock_slack_cls.return_value = mock_slack

        # サマリデータが返らないケースで早期リターンさせる
        mock_bq.fetch_weekly_summary.return_value = None

        main()

        # fetch_weekly_summary が正しい引数で呼ばれたか
        expected_yesterday = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
        mock_bq.fetch_weekly_summary.assert_called_once_with(
            "UC_test_channel_id", today_str=expected_yesterday
        )

    @patch.dict(os.environ, {"YOUTUBE_CHANNEL_ID": "UC_test_channel_id"})
    @patch("src.main_weekly.BigQueryClient")
    @patch("src.main_weekly.GeminiClient")
    @patch("src.main_weekly.SlackClient")
    def test_main_weekly_full_flow_with_pipe_separated_prompt(
        self, mock_slack_cls, mock_gemini_cls, mock_bq_cls
    ):
        """サマリデータが存在する場合にパイプ区切りのKPIサマリが生成され、Slack送信まで完了すること"""
        mock_bq = MagicMock()
        mock_gemini = MagicMock()
        mock_slack = MagicMock()

        mock_bq_cls.return_value = mock_bq
        mock_gemini_cls.return_value = mock_gemini
        mock_slack_cls.return_value = mock_slack

        mock_bq.fetch_weekly_summary.return_value = {
            "channel_title": "テストチャンネル",
            "start_date": "2026-11-09",
            "end_date": "2026-11-15",
            "subscriber_growth": 10,
            "view_growth": 2000,
            "like_growth": 50,
            "current_subscribers": 100,
            "current_views": 50000,
            "current_likes": 1000,
        }
        mock_gemini.generate_strategy_advice.return_value = "アドバイス"

        main()

        # Gemini呼び出し時の引数 kpi_summary_text がパイプ区切り1行形式であることを検証
        mock_gemini.generate_strategy_advice.assert_called_once()
        kpi_arg = mock_gemini.generate_strategy_advice.call_args[0][0]
        self.assertIn("[期間] 2026-11-09〜2026-11-15 | ", kpi_arg)
        self.assertIn("登録増: +10人 (現100人) | ", kpi_arg)
        self.assertIn("再生増: +2,000回 (現50,000回) | ", kpi_arg)
        self.assertIn("いいね増: +50回 (現1,000回) | ", kpi_arg)
        self.assertIn("CVR: 0.50%", kpi_arg)

        mock_slack.send_weekly_report.assert_called_once()

if __name__ == "__main__":
    unittest.main()
