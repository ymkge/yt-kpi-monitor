# yt-kpi-monitor

## 概要
`yt-kpi-monitor` は、YouTubeチャンネルの日々のKPI（登録者数、再生数、いいね数など）を自動取得・蓄積し、Slackへのアラート通知やLLMを用いた戦略的アドバイスの自動生成を行うデータ運用基盤です。

クラウドDWHとサーバーレスアーキテクチャを組み合わせることで、完全無料枠（Free Tier）での自律的な運用を実現しています。

## 主な機能
* **日次KPIアラート（Daily Monitor）**
  * 毎日定期的にYouTube Data APIから最新のチャンネルKPIを取得。
  * 前回実行時からの差分（登録者数やいいね数の増加）を検知し、Slackへ即時通知。
  * 取得したスナップショットデータをGoogle BigQueryへ蓄積。
* **週次/月次 戦略レポート（Weekly/Monthly Advisor）**
  * BigQueryに蓄積されたデータおよびYouTube Analytics APIの詳細指標を集計。
  * 集計データを元に、Gemini APIが「良かった点」「改善点」「次週に向けたコンテンツ戦略」を推論。
  * データアナリスト視点のサマリレポートとしてSlackへ自動投稿。

## アーキテクチャ構成
本プロジェクトは以下の技術スタックで構成されており、ステートレスかつインフラ管理が不要なアーキテクチャを採用しています。

* **実行環境**: GitHub Actions (cronスケジューラ)
* **データソース**: YouTube Data API v3 / YouTube Analytics API
* **データウェアハウス**: Google BigQuery (Google Cloud サンドボックス環境)
* **LLMエンジン**: Gemini API (Google AI Studio)
* **通知先**: Slack (Incoming Webhook)

## ディレクトリ構成
```text
yt-kpi-monitor/
├── .github/workflows/   # GitHub Actionsの実行定義ファイル
├── config/query/        # BigQuery実行用のSQLファイル群
├── src/                 # Pythonのソースコード（APIクライアント、メインロジック）
├── README.md            # 本ドキュメント
├── GEMINI.md            # AIアシスタント開発用コンテキスト・ルール定義
└── requirements.txt     # 依存ライブラリ
```

## 必要な環境変数とシークレット

セキュリティ観点から、各種APIキーやクレデンシャル情報はコードに含めず、すべて **GitHub Secrets** に登録して実行時に参照します。

* **`YOUTUBE_API_KEY`**: YouTube Data API v3 実行用のキー
* **`YOUTUBE_OAUTH_CLIENT_ID` / `CLIENT_SECRET`**: YouTube Analytics API実行用のOAuth情報
* **`GCP_SERVICE_ACCOUNT_KEY`**: BigQueryアクセス用のサービスアカウントのJSONキー
* **`GEMINI_API_KEY`**: Gemini API実行用のキー
* **`SLACK_WEBHOOK_URL`**: 通知先SlackチャンネルのWebhook URL

---

## 今後の拡張予定 (Roadmap)

- [ ] 初期KPI取得および差分通知機能の実装
- [ ] BigQueryへのデータ蓄積フロー構築
- [ ] Gemini API連携およびプロンプトエンジニアリングの最適化
- [ ] dbtを用いたデータモデリングの導入検証

---

