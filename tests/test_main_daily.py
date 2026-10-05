import unittest
from datetime import datetime, timezone, timedelta

class TestMainDailyRecentVideosProcessing(unittest.TestCase):
    """
    main_daily.py の recent_videos 走査・メトリクス統合ロジックの単体テスト
    """
    def _process_recent_videos(self, recent_videos, metrics_data, impressions_data, previous_video_kpis, initial_averages, now_jst):
        """main_daily.py L187〜L307 のロジックを抽出して検証するヘルパー"""
        recent_videos_kpis = []
        JST = timezone(timedelta(hours=9))

        for v in recent_videos:
            v_id = v["video_id"]
            analytics_reflected = v_id in metrics_data
            v_metrics = dict(metrics_data.get(v_id, {})) if analytics_reflected else {}
            prev_v = previous_video_kpis.get(v_id, {})
            rt_views = v.get("realtime_views")
            rt_likes = v.get("realtime_likes")
            if rt_views is None:
                rt_views = prev_v.get("views", 0)
            if rt_likes is None:
                rt_likes = prev_v.get("likes", 0)

            v_metrics["views"] = rt_views
            v_metrics["likes"] = rt_likes

            v_metrics["red_views"] = v_metrics.get("red_views") if analytics_reflected else None
            v_metrics["engaged_views"] = v_metrics.get("engaged_views") if analytics_reflected else None
            v_metrics["subscribers_gained"] = v_metrics.get("subscribers_gained") if analytics_reflected else None
            v_metrics["average_view_duration"] = v_metrics.get("average_view_duration") if analytics_reflected else None

            v_impr = impressions_data.get(v_id)
            if v_impr and v_impr.get("impressions", 0) > 0:
                v_metrics["impressions"] = v_impr["impressions"]
                v_metrics["ctr"] = v_impr["ctr"]
            else:
                v_metrics["impressions"] = None
                v_metrics["ctr"] = None

            # 前日比差分の算出
            diffs = {}
            def calc_diff(curr_val, prev_val):
                if curr_val is None or prev_val is None:
                    return None
                return curr_val - prev_val

            if prev_v:
                diffs["views"] = calc_diff(v_metrics["views"], prev_v.get("views"))
                diffs["engaged_views"] = calc_diff(v_metrics["engaged_views"], prev_v.get("engaged_views"))
                diffs["likes"] = calc_diff(v_metrics["likes"], prev_v.get("likes"))
                diffs["subscribers_gained"] = calc_diff(v_metrics["subscribers_gained"], prev_v.get("subscribers_gained"))
                diffs["average_view_duration"] = calc_diff(v_metrics["average_view_duration"], prev_v.get("average_view_duration"))
                diffs["impressions"] = calc_diff(v_metrics["impressions"], prev_v.get("impressions"))

                curr_ctr = v_metrics["ctr"]
                prev_ctr = prev_v.get("ctr")
                if curr_ctr is not None and prev_ctr is not None:
                    diffs["ctr"] = round(curr_ctr - prev_ctr, 2)
                else:
                    diffs["ctr"] = None
            else:
                diffs = {
                    "views": None,
                    "engaged_views": None,
                    "likes": None,
                    "subscribers_gained": None,
                    "average_view_duration": None,
                    "impressions": None,
                    "ctr": None
                }

            v_metrics["diff"] = diffs

            # エンゲージ率の算出
            curr_v_count = v_metrics["views"]
            curr_eng_v = v_metrics.get("engaged_views")
            if curr_v_count and curr_v_count > 0 and curr_eng_v is not None:
                v_metrics["engage_rate"] = min(100.0, (curr_eng_v / curr_v_count) * 100.0)
            else:
                v_metrics["engage_rate"] = None

            # 初速分析
            age_days = None
            if v.get("published_at"):
                try:
                    pub_time_jst = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")).astimezone(JST)
                    age_days = (now_jst.date() - pub_time_jst.date()).days
                except Exception:
                    age_days = None

            curr_views = v_metrics["views"]
            curr_likes = v_metrics["likes"]
            like_rate = (curr_likes / curr_views * 100) if curr_views and curr_views > 0 else None

            pace_score = None
            avg_v = None
            ratio_pct = None

            if age_days in [1, 3, 7] and age_days in initial_averages:
                avg_info = initial_averages[age_days]
                avg_v = avg_info.get("avg_views", 0)
                sample_cnt = avg_info.get("sample_video_count", 0)
                if sample_cnt >= 3 and avg_v > 0:
                    ratio = (curr_views / avg_v) - 1.0
                    ratio_pct = ratio * 100
                    if ratio >= 0.50:
                        pace_score = "★★★★★ (🚀 大好調!)"
                    elif ratio >= 0.20:
                        pace_score = "★★★★☆ (👍 好調)"
                    elif ratio >= -0.20:
                        pace_score = "★★★☆☆ (⚖️ 標準ペース)"
                    elif ratio >= -0.40:
                        pace_score = "★★☆☆☆ (📉 やや低調)"
                    else:
                        pace_score = "★☆☆☆☆ (⚠️ 伸び悩み)"

            v_metrics["initial_analysis"] = {
                "age_days": age_days,
                "like_rate": like_rate,
                "pace_score": pace_score,
                "avg_views": avg_v,
                "ratio_pct": ratio_pct
            }

            recent_videos_kpis.append({
                "video_id": v_id,
                "title": v["title"],
                "published_at": v["published_at"],
                "metrics": v_metrics
            })

        return recent_videos_kpis

    def test_metrics_integration_success(self):
        """通常の動画メトリクス統合が NameError なく正常に完了すること"""
        now_jst = datetime(2026, 10, 5, 0, 48, 0, tzinfo=timezone(timedelta(hours=9)))
        recent_videos = [
            {
                "video_id": "vid1",
                "title": "集中ピアノ",
                "published_at": "2026-10-04T09:00:00Z",
                "realtime_views": 120,
                "realtime_likes": 6
            }
        ]
        metrics_data = {
            "vid1": {
                "red_views": 10,
                "engaged_views": 15,
                "subscribers_gained": 1,
                "average_view_duration": 300
            }
        }
        impressions_data = {"vid1": {"impressions": 1000, "ctr": 5.5}}
        previous_video_kpis = {
            "vid1": {"views": 100, "likes": 5, "engaged_views": 10, "subscribers_gained": 0, "impressions": 800, "ctr": 5.0}
        }
        initial_averages = {1: {"avg_views": 50.0, "avg_likes": 3.0, "sample_video_count": 10}}

        res = self._process_recent_videos(recent_videos, metrics_data, impressions_data, previous_video_kpis, initial_averages, now_jst)

        self.assertEqual(len(res), 1)
        m = res[0]["metrics"]
        self.assertEqual(m["views"], 120)
        self.assertEqual(m["likes"], 6)
        self.assertEqual(m["diff"]["views"], 20)
        self.assertEqual(m["diff"]["likes"], 1)
        self.assertEqual(m["diff"]["subscribers_gained"], 1)
        self.assertEqual(m["impressions"], 1000)
        self.assertEqual(m["ctr"], 5.5)
        self.assertEqual(m["engage_rate"], 12.5) # 15 / 120 * 100
        self.assertIsNotNone(m["initial_analysis"]["pace_score"])

    def test_metrics_integration_omitted_video(self):
        """metrics_data に動画IDが含まれない（API未反映）場合でも NameError や例外なくフォールバックすること"""
        now_jst = datetime(2026, 10, 5, 0, 48, 0, tzinfo=timezone(timedelta(hours=9)))
        recent_videos = [
            {
                "video_id": "vid_new",
                "title": "新着動画",
                "published_at": "2026-10-04T22:00:00Z",
                "realtime_views": 5,
                "realtime_likes": 1
            }
        ]
        metrics_data = {} # API未反映で空
        impressions_data = {}
        previous_video_kpis = {}
        initial_averages = {}

        res = self._process_recent_videos(recent_videos, metrics_data, impressions_data, previous_video_kpis, initial_averages, now_jst)

        self.assertEqual(len(res), 1)
        m = res[0]["metrics"]
        self.assertEqual(m["views"], 5)
        self.assertEqual(m["likes"], 1)
        self.assertIsNone(m["engaged_views"])
        self.assertIsNone(m["subscribers_gained"])
        self.assertIsNone(m["impressions"])
        self.assertIsNone(m["ctr"])
        self.assertIsNone(m["engage_rate"])

    def test_metrics_integration_zero_views(self):
        """ゼロ再生の新規動画でも ZeroDivisionError 等なく安全に動作すること"""
        now_jst = datetime(2026, 10, 5, 0, 48, 0, tzinfo=timezone(timedelta(hours=9)))
        recent_videos = [
            {
                "video_id": "vid_zero",
                "title": "公開直後動画",
                "published_at": "2026-10-05T00:00:00Z",
                "realtime_views": 0,
                "realtime_likes": 0
            }
        ]
        metrics_data = {}
        impressions_data = {}
        previous_video_kpis = {}
        initial_averages = {}

        res = self._process_recent_videos(recent_videos, metrics_data, impressions_data, previous_video_kpis, initial_averages, now_jst)

        self.assertEqual(len(res), 1)
        m = res[0]["metrics"]
        self.assertEqual(m["views"], 0)
        self.assertEqual(m["likes"], 0)
        self.assertIsNone(m["engage_rate"])
        self.assertIsNone(m["initial_analysis"]["like_rate"])

if __name__ == "__main__":
    unittest.main()
