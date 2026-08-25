# yt-kpi-monitor

## 概要
`yt-kpi-monitor` は、YouTubeチャンネルの日々のKPI（登録者数、再生数、いいね数など）を自動取得・蓄積し、Slackへのアラート通知やGemini AIを用いた戦略的アドバイスの自動生成を行うデータ運用基盤です。

GitHub ActionsとGoogle Cloudを活用することで、完全無料枠（Free Tier）での自律的な運用を実現しています。

## 主な機能
*   **日次KPIアラート（Daily Monitor）**
    *   毎日 19:00 (JST) に最新のチャンネル統計を取得。
    *   前回実行時からの差分（登録者数やいいね数の増加）を検知し、Slackへ通知。
    *   **直近14日動画の詳細KPI＆前日比表示**
        *   直近14日以内に公開された動画の各KPI（再生数、いいね数、登録者増、平均視聴時間、インプレッション数、CTR）において、前回計測時からの前日比増減（例: `+150 回`, `+1分15秒`, `+0.15%pt`）を分かりやすく表記（#54）。
        *   いいね数が減少（取り消し）された動画の自動検出・通知機能（#53）。
    *   **動画のクリック率 (CTR) 改善アラート表示（音楽BGMチャンネル向け調整）**
        *   CTRの値に応じた評価ラベル（絵文字＋アクション指標）を付与。
        *   判定閾値: `🟢 優秀 (4.0%以上)`, `🟡 標準 (2.0%以上)`, `🔴 要改善 (2.0%未満)`。
        *   APIデータ遅延や公開直後のデータ不足時には `⚪️ 集計中 (データ反映待ち)` と表示し誤判定を防止。
    *   取得したデータを Google BigQuery へ永久蓄積（`ARRAY_AGG` + `STRUCT` による直近現在値および純増減数の高精度選出 #59）。
*   **週次・月次AI戦略レポート（Weekly & Monthly Advisor）**
    *   毎週月曜 0:00 (JST) および毎月1日 0:00 (JST) に集計を実行。
    *   **ナレッジベース連携によるAI分析精度の向上 (RAG Engine #51)**
        *   `config/knowledge/` ディレクトリに置かれた運用知識（Markdownファイル）を自動読み込み。
        *   現在のチャンネル登録者数フェーズ（例: 100人未満、1,000人未満など）にベストマッチするナレッジを自働抽出し、Gemini のプロンプトへ注入。
        *   `.md` ファイルを追加・更新するだけで、コード修正なしで自由にナレッジを拡張可能。
    *   **Gemini API の高レジリエンス＆耐障害性 (#57)**
        *   Google AI サーバー混雑（503）発生時に、`gemini-flash-latest` から `gemini-flash-lite-latest` へ自動フォールバックして再試行。
        *   万が一全モデルで AI 生成が応答しない場合でも、基本数値レポートや動画ランキングを安全に完走して Slack に受領させる安全装置を搭載。

## アーキテクチャ構成
*   **実行環境**: GitHub Actions (cronスケジューラ)
*   **データソース**: YouTube Data API v3 & YouTube Analytics API v2
*   **データウェアハウス**: Google BigQuery (Sandbox環境 / Batch Load方式)
*   **AIエンジン**: Gemini API (`gemini-flash-latest` / `gemini-flash-lite-latest`)
*   **ナレッジベース (RAG)**: ディレクトリ駆動型ナレッジエンジン (`config/knowledge/*.md`)
*   **通知先**: Slack (Incoming Webhook & Bot Token スレッド投稿)

## セットアップ手順

### 1. Google Cloud 設定
1.  BigQueryでデータセットを作成。
2.  以下の SQL ファイルを実行し、テーブルを作成する。
    *   `config/query/create_channel_kpis_table.sql` (チャンネル全体のKPI蓄積用)
    *   `config/query/create_video_kpis_table.sql` (動画ごとの日次KPI蓄積用)
    *   ※ SQL内の `{{project_id}}` 等は自身の環境に置換すること。
3.  サービスアカウントを作成し、「BigQuery データ編集者」「BigQuery ジョブユーザー」権限を付与して JSON キーを発行。

### 2. GitHub Secrets の登録
リポジトリの **Settings > Secrets and variables > Actions** に以下の値を登録してください。

| 名前 | 内容 |
| :--- | :--- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 のキー |
| `YOUTUBE_CHANNEL_ID` | 監視対象のチャンネルID (UC...) |
| `YOUTUBE_OAUTH_CLIENT_ID` | YouTube Analytics OAuth 2.0 クライアントID |
| `YOUTUBE_OAUTH_CLIENT_SECRET` | YouTube Analytics OAuth 2.0 クライアントシークレット |
| `YOUTUBE_OAUTH_REFRESH_TOKEN` | OAuth 2.0 リフレッシュトークン |
| `GCP_PROJECT_ID` | GCP プロジェクトID |
| `GCP_DATASET_ID` | BigQuery データセット名 |
| `GCP_SERVICE_ACCOUNT_KEY` | サービスアカウントのJSONキー内容すべて（改行含めそのまま） |
| `GEMINI_API_KEY` | Google AI Studio のAPIキー |
| `GEMINI_MODEL` | プライマリGeminiモデル名（任意、未指定時は `gemini-flash-latest`） |
| `GEMINI_FALLBACK_MODEL` | フォールバックGeminiモデル名（任意、未指定時は `gemini-flash-lite-latest`） |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |

### 3. ナレッジベース (RAG) の活用方法
`config/knowledge/` 配下に新しい Markdown ファイル（`.md`）を追加・更新することで、AI に踏まえさせたい運用知見をいつでも拡張できます。

**ファイル記述例 (`config/knowledge/my_strategy.md`)**:
```markdown
---
title: 登録者100人未満のチャンネル成長戦略
min_subscribers: 0
max_subscribers: 100
---

（ここにアドバイスの前提とさせたい知識やYouTube運用ガイドラインを記載）
```
- `min_subscribers` / `max_subscribers`: 対象とする登録者数範囲を指定すると、チャンネルの成長段階に合わせて自動選択されます。


## ディレクトリ構成
```text
yt-kpi-monitor/
├── .agents/
│   └── AGENTS.md        # Antigravity用の開発ルール（自動認識されます）
├── .github/workflows/   # GitHub Actions (日次/週次/月次)
├── config/
│   ├── knowledge/       # ナレッジベース用 Markdown ファイル (*.md)
│   │   └── subscribers_under_100.md
│   └── query/           # BigQuery実行用SQL
├── scripts/             # ローカル実行用補助スクリプト
│   └── get_oauth_tokens.py
├── src/                 # Pythonソースコード
│   ├── youtube_client.py
│   ├── youtube_analytics_client.py
│   ├── bigquery_client.py
│   ├── gemini_client.py
│   ├── knowledge_manager.py
│   ├── slack_client.py
│   ├── main_daily.py
│   ├── main_weekly.py
│   └── main_monthly.py
├── requirements.txt
└── README.md            # 本ドキュメント
```


## 開発計画・ロードマップ

### フェーズ1: 環境構築 ＆ BigQueryスキーマ設計 (完了)
- [x] 必要なPythonライブラリの選定（`requirements.txt` の作成）
- [x] BigQueryのテーブル設計
- [x] ローカル検証環境用の環境変数定義サンプルの作成

### フェーズ2: 日次KPI取得 ＆ 差分通知の実装 (完了)
- [x] `youtube_client.py`: YouTube Data API v3 を用いたチャンネル情報・動画情報の取得処理
- [x] `bigquery_client.py`: 最新KPIの保存および前回データとの比較用クエリの実行処理
- [x] `slack_client.py`: 登録者数やいいね数が増えた際のメッセージフォーマット整形とWebhook送信
- [x] `slack_client.py`: 直近14日以内に公開された動画に対するCTR評価アラート機能の実装（閾値: 2.0% / 4.0%）およびデータ遅延時のハンドリング（#46）
- [x] `main_daily.py`: 直近14日動画の詳細KPIにおける前日比差分表示（#54）およびいいね減少通知（#53）
- [x] `.github/workflows/daily_kpi_alert.yml`: GitHub Actionsの設定

### フェーズ3: 週次/月次レポート ＆ Gemini/RAG連携の実装 (完了)
- [x] `gemini_client.py`: Google AI Studio経由でGemini APIを呼び出す処理の実装および過負荷時のフォールバック機能（#57）
- [x] `knowledge_manager.py`: ファイルベースのナレッジエンジン (RAG) によるアドバイス精度向上機能の実装（#51）
- [x] `main_weekly.py`: 週次集計データとAIアドバイスを統合してSlackへリッチテキストで投稿するスクリプト
- [x] `main_monthly.py`: 月次レポーティング、CVR算出、月前月比比較の実装（#43）
- [x] `.github/workflows/weekly_report.yml` / `monthly_report.yml`: 定期レポート用のGitHub Actionsの設定
- [x] BigQueryにおける `ARRAY_AGG` + `STRUCT` を用いた直近最新値および純増減数の算出クエリ改修（#58, #59）

### 今後の拡張予定 (Next Steps)
- [ ] エラー発生時のSlack通知強化
- [ ] Looker Studio によるデータ可視化