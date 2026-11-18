import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import os

from src.main_weekly import main

JST = timezone(timedelta(hours=9))

class TestMainWeekly(unittest.TestCase):
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
    def test_main_weekly_full_flow(
        self, mock_slack_cls, mock_gemini_cls, mock_bq_cls
    ):
        """サマリデータが存在する場合に Slack 送信まで正常に完了すること"""
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

        mock_gemini.generate_strategy_advice.assert_called_once()
        mock_slack.send_weekly_report.assert_called_once()

if __name__ == "__main__":
    unittest.main()
