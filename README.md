# yt-kpi-monitor

## 概要
`yt-kpi-monitor` は、YouTubeチャンネルの日々のKPI（登録者数、再生数、いいね数など）を自動取得・蓄積し、Slackへのアラート通知やGemini AIを用いた戦略的アドバイスの自動生成を行うデータ運用基盤です。

GitHub ActionsとGoogle Cloudを活用することで、完全無料枠（Free Tier）での自律的な運用を実現しています。

## 主な機能
*   **日次KPIアラート（Daily Monitor）**
    *   毎日 0:00 (JST) に最新のチャンネル統計を取得。
    *   前回実行時からの差分（登録者数やいいね数の増加）を検知し、Slackへ通知。
    *   取得したデータを Google BigQuery へ永久蓄積。
*   **週次AI戦略レポート（Weekly Advisor）**
    *   毎週月曜 0:00 (JST) に直近1週間のデータを集計。
    *   集計データを元に、Gemini 2.0 Flashが「現状分析」「良かった点」「改善案」「翌週のアクション」を生成。
    *   データアナリスト視点のサマリレポートとしてSlackへ自動投稿。

## アーキテクチャ構成
*   **実行環境**: GitHub Actions (cronスケジューラ)
*   **データソース**: YouTube Data API v3
*   **データウェアハウス**: Google BigQuery
*   **AIエンジン**: Gemini 2.0 Flash (Google AI Studio)
*   **通知先**: Slack (Incoming Webhook)

## セットアップ手順

### 1. Google Cloud 設定
1.  BigQueryでデータセットを作成。
2.  `config/query/create_channel_kpis_table.sql` を実行し、`channel_kpis` テーブルを作成。
3.  サービスアカウントを作成し、「BigQuery データ編集者」「BigQuery ジョブユーザー」権限を付与して JSON キーを発行。

### 2. GitHub Secrets の登録
リポジトリの **Settings > Secrets and variables > Actions** に以下の値を登録してください。

| 名前 | 内容 |
| :--- | :--- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 のキー |
| `YOUTUBE_CHANNEL_ID` | 監視対象のチャンネルID (UC...) |
| `GCP_PROJECT_ID` | GCP プロジェクトID |
| `GCP_DATASET_ID` | BigQuery データセット名 |
| `GCP_SERVICE_ACCOUNT_KEY` | サービスアカウントのJSONキー内容すべて |
| `GEMINI_API_KEY` | Google AI Studio のAPIキー |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |

## ディレクトリ構成
```text
yt-kpi-monitor/
├── .github/workflows/   # GitHub Actions (日次/週次)
├── config/query/        # BigQuery実行用SQL
├── src/                 # Pythonソースコード
│   ├── youtube_client.py
│   ├── bigquery_client.py
│   ├── gemini_client.py
│   ├── slack_client.py
│   ├── main_daily.py
│   └── main_weekly.py
├── requirements.txt
└── GEMINI.md            # 開発ルール・詳細設計書
```

## 今後の拡張予定
- [ ] YouTube Analytics API (OAuth) 連携による詳細分析
- [ ] エラー発生時のSlack通知強化
- [ ] Looker Studio によるデータ可視化
