# GEMINI.md - YouTube KPI Monitor 開発計画・設計書

本ドキュメントは、YouTubeの各種KPIを自動取得し、Slack通知およびGemini APIによる戦略アドバイスレポートを完全無料枠で運用するための実装計画、および開発ルールをまとめたものである。Gemini CLIを用いた開発において、このコンテキストを最優先に参照すること。

---

## 1. プロジェクト概要 & ゴール

- **目的**: YouTube Data API / Analytics APIからチャンネル運用データを取得し、「日次の増分通知」と「週次・月次のAI戦略アドバイス」を完全自動化する。
- **インフラ費用**: 完全無料（Free Tierの範囲内での運用）。
- **主要機能**:
  1. 日次バッチ: 登録者数・いいね数の差分検知とSlackアラート通知。最新KPIのBigQuery保存。
  2. 週次/月次バッチ: 期間内データの集計、Gemini APIへのコンテキスト投入による戦略アドバイス生成、Slackへのリッチレポート投稿。

---

## 2. 技術スタック & アーキテクチャ

- **実行環境 (Orchestration)**: GitHub Actions (cronによるスケジュール実行 / ステートレス環境)
- **データ蓄積 (DWH)**: Google BigQuery (サンドボックス環境 / 無料枠10GB・1TBクエリ内)
- **AIエンジン (LLM)**: Gemini API (Google AI Studio経由 / 無料枠利用)
- **言語・主要ライブラリ**: Python 3.11+, `google-cloud-bigquery`, `google-genai`, `requests`
- **通知先**: Slack (Incoming Webhook)

---

## 3. 開発・実装ルール (最重要)

開発を進める上で、以下のコーディング規約およびセキュリティ規約を厳守すること。

### 3.1. セキュリティ規約
- **認証情報の管理**: 
  - サービスアカウントキーや各種APIトークン（Slack Webhook URL, Gemini API Key, YouTube API Key）は、絶対にコード内に直書きしない。
  - すべて環境変数（GitHub Secrets）から読み込む構成にすること。
  - セキュリティリスクを最小化するため、SSH鍵による認証ではなく、Personal Access Token (PAT) やサービスアカウントによる適切なスコープ管理を行う。

### 3.2. SQLコーディング規約 (BigQuery)
- **カンマの配置**: 列定義やSELECT文における**「前カンマ（leading commas）」は一切禁止**とする。必ず後ろカンマ（trailing commas）で記述すること。
- **予約語**: SQLのキーワード（SELECT, FROM, WHERE, GROUP BYなど）はすべて大文字で統一すること。
- **データ型**: 日時は `TIMESTAMP` または `DATETIME` 型を適切に使い分け、タイムゾーン（アジア/東京）を意識した設計にすること。

---

## 4. ディレクトリ構成（予定）

```text
yt-kpi-monitor/
├── .github/
│   └── workflows/
│       ├── daily_kpi_alert.yml
│       └── weekly_report.yml
├── config/
│   └── query/
│       ├── fetch_previous_kpi.sql
│       └── aggregate_weekly_summary.sql
├── src/
│   ├── __init__
│   ├── youtube_client.py
│   ├── bigquery_client.py
│   ├── gemini_client.py
│   ├── slack_client.py
│   ├── main_daily.py
│   └── main_weekly.py
├── requirements.txt
├── README.md
└── GEMINI.md
```

## 5. 実行計画（フェーズ別タスク）

### フェーズ1: 環境構築 ＆ BigQueryスキーマ設計
- [x] 必要なPythonライブラリの選定（`requirements.txt` の作成）。
- [x] BigQueryのテーブル設計。
  - `channel_kpis`（日次スナップショット: 日付、登録者数、総再生数、総いいね数など）。
  - **※ SQLは後ろカンマ規約を厳守して作成する。**
- [x] ローカル検証環境用の環境変数定義サンプルの作成。

### フェーズ2: 日次KPI取得 ＆ 差分通知の実装
- [x] `youtube_client.py`: YouTube Data API v3 を用いたチャンネル情報・動画情報の取得処理。
- [x] `bigquery_client.py`: 最新KPIの保存および前回データとの比較用クエリの実行処理。
- [x] `slack_client.py`: 登録者数やいいね数が増えた際のメッセージフォーマット整形とWebhook送信。
- [x] `main_daily.py`: 上記を統合した日次実行スクリプト。
- [x] `.github/workflows/daily_kpi_alert.yml`: GitHub Actionsの設定。

### フェーズ3: 週次/月次レポート ＆ Gemini連携の実装
- [ ] YouTube Analytics APIから、より詳細な指標（視聴維持率、トラフィックソースなど）を取得する処理の追加。
- [x] `gemini_client.py`: Google AI Studio経由でGemini APIを呼び出す処理の実装。
- [x] 戦略アドバイスを引き出すための、Markdown形式のプロンプトテンプレート設計。
- [x] `main_weekly.py`: 週次集計データとAIアドバイスを統合してSlackへリッチテキストで投稿するスクリプト。
- [x] `.github/workflows/weekly_report.yml`: 定期レポート用のGitHub Actionsの設定。

---

## 6. Gemini CLIへの指示出しテンプレート

実装を開始する際は、以下のプロンプト形式で指示を行う。

**【指示テンプレート】**
> GEMINI.md に記載されている「開発・実装ルール」および「フェーズX」のタスクに基づき、〇〇のスクリプトを実装してください。SQLやコードブロックの出力規約に注意してください。
