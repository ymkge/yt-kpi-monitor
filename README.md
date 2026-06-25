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
    *   集計データを元に、Gemini 3.5 Flashが「現状分析」「良かった点」「改善案」「翌週のアクション」を生成。
    *   データアナリスト視点のサマリレポートとしてSlackへ自動投稿。

## アーキテクチャ構成
*   **実行環境**: GitHub Actions (cronスケジューラ)
*   **データソース**: YouTube Data API v3 & YouTube Analytics API v2
*   **データウェアハウス**: Google BigQuery (Sandbox環境 / Batch Load方式)
*   **AIエンジン**: Gemini 3.5 Flash (Google AI Studio)
*   **通知先**: Slack (Incoming Webhook)

## セットアップ手順

### 1. Google Cloud 設定
1.  BigQueryでデータセットを作成。
2.  `config/query/create_channel_kpis_table.sql` を実行し、`channel_kpis` テーブルを作成。
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
| `GEMINI_MODEL` | 使用するGeminiモデル名（任意、未指定時は `gemini-3.5-flash`） |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |

### 3. YouTube Analytics API (OAuth2) セットアップ
週次レポートで動画ランキング（再生数・高評価数）を機能させるために、以下の手順でOAuth2認証を通す必要があります。

1. **Google Cloud Console** で以下を実施：
   * `YouTube Analytics API` を有効化する。
   * 「OAuth 同意画面」を設定（ユーザーの種類: 外部、テストユーザーに自身のYouTubeアカウントを追加）。
     * 必要なスコープ: `https://www.googleapis.com/auth/yt-analytics.readonly` および `https://www.googleapis.com/auth/youtube.readonly`
   * 「認証情報」から **OAuth 2.0 クライアント ID** (種類: デスクトップ アプリ) を作成。
   * 作成したクライアントIDのJSONキーをダウンロードし、プロジェクトルートに `client_secret.json` として配置。
2. **リフレッシュトークンの取得**:
   * ローカル環境で以下のスクリプトを実行：
     ```bash
     python scripts/get_oauth_tokens.py
     ```
   * ブラウザが起動するので、上記で登録したテストユーザーアカウントでログイン・認証を承認します。
   * コンソールに出力された `Refresh Token`, `Client ID`, `Client Secret` をコピーします。
3. **環境変数の設定**:
   * コピーした値を `.env` または GitHub Secrets にそれぞれ設定します。
   * ※ 設定完了後、ローカルの `client_secret.json` は不要なため削除してください。


## 手動実行手順
定期実行（GitHub Actionsのcron）を待たずに、手動で日次モニターや週次レポートを実行する方法は以下の2通りあります。

### 1. ローカル環境での手動実行
事前に `.env` の設定と依存ライブラリのインストールを完了した上で、プロジェクトのルートディレクトリで以下のコマンドを実行します。

* **日次KPIアラートの実行**
  ```bash
  python3 -m src.main_daily
  ```

* **週次AI戦略レポートの実行**
  ```bash
  python3 -m src.main_weekly
  ```

### 2. GitHub Actions 上での手動実行
GitHubリポジトリ上で手動実行（Workflow Dispatch）が可能です。

1. GitHub リポジトリの **Actions** タブを開きます。
2. 左側のメニューから実行したいワークフローを選択します：
   * **Daily KPI Alert**（日次モニター）
   * **Weekly Strategy Report**（週次レポート）
3. 画面右側に表示される **Run workflow** ドロップダウンをクリックし、**Run workflow** ボタンを押して実行します。


## ディレクトリ構成
```text
yt-kpi-monitor/
├── .agents/
│   └── AGENTS.md        # Antigravity用の開発ルール（自動認識されます）
├── .github/workflows/   # GitHub Actions (日次/週次)
├── config/query/        # BigQuery実行用SQL
├── scripts/             # ローカル実行用補助スクリプト
│   └── get_oauth_tokens.py
├── src/                 # Pythonソースコード
│   ├── youtube_client.py
│   ├── youtube_analytics_client.py
│   ├── bigquery_client.py
│   ├── gemini_client.py
│   ├── slack_client.py
│   ├── main_daily.py
│   └── main_weekly.py
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
- [x] `main_daily.py`: 上記を統合した日次実行スクリプト
- [x] `.github/workflows/daily_kpi_alert.yml`: GitHub Actionsの設定

### フェーズ3: 週次/月次レポート ＆ Gemini連携の実装 (完了)
- [x] `gemini_client.py`: Google AI Studio経由でGemini APIを呼び出す処理の実装
- [x] `main_weekly.py`: 週次集計データとAIアドバイスを統合してSlackへリッチテキストで投稿するスクリプト
- [x] `.github/workflows/weekly_report.yml`: 定期レポート用のGitHub Actionsの設定
- [x] YouTube Analytics APIから、より詳細な指標（視聴維持率、トラフィックソースなど）を取得する処理の追加

### 今後の拡張予定 (Next Steps)
- [x] YouTube Analytics API (OAuth) 連携による詳細分析
- [ ] エラー発生時のSlack通知強化
- [ ] Looker Studio によるデータ可視化
- [x] 週次レポーティングの強化 (直近28日間の再生数のランキング1-3位、高評価数（いいね数）のランキング1-3位を連携する)
- [x] [改善]週次レポートのLLMアドバイス内容が長文の為、要点を押さえたレポートを出せるようにプロンプト改善する #23
- [ ] 月次レポーティングの導入 (月間での累積でのランキングや月間サマリー情報、LLMでの改善ポイント抽出レポートなど) #25
- [ ] [改善]デイリーレポートが2日連続同じ値になってしまっている。 #26
  - 6/23と6/24のレポート内容が全く同じでした。再生数が2日連続同じにはならないはずですので、デイリーの時刻時間を調整することで、この状態を改善したい。なお、6/23は03:51, 6/24は02:20にslackにレポートが届いています。現状把握をして改善案を検討して確定する。
- [x] [改善]デイリーレポートで、直近14日以内にパブリッシュされた動画のKPI情報を見れるようにしたい #27
  - 目的は、直近リリースされた動画のKPI（動画公開時刻、YouTube Premium の視聴回数、新しい視聴者数、リピーター、視聴回数、チャンネル登録者	、平均視聴時間、インプレッション数、インプレッションのクリック率 (%)）をデイリーで把握する為です。すぐにサムネイルやタイトルなどの改善ができるようにしたいです。
- [ ] [改善]現在slackに設定したDemo Appにレポート投稿をさせているが、アプリのキャラクター設定を行うことで、親しみやすいレポート内容にしたい #28
  - slack上のアプリの登録変更で対応する。またそのキャラクターの設定内容によって、レポート内容の文面をキャラクターの口癖などになるように修正が必要（LLMのプロンプトのキャラクター設定が必要）

