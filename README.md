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
| `GEMINI_MODEL` | 使用するGeminiモデル名（任意、未指定時は `gemini-flash-latest`。モデルの自動更新に伴い挙動が崩れる場合は、特定の静的モデル名を設定して固定することを推奨します） |
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

### 今後の拡張予定 (Next Steps) *この中で完了したタスクはREADME.mdから削除していく（ISSUEに履歴を残している為）
- [ ] エラー発生時のSlack通知強化
- [ ] Looker Studio によるデータ可視化
- [ ] 月次レポーティングの導入 (月間での累積でのランキングや月間サマリー情報、LLMでの改善ポイント抽出レポートなど) #25

- #25の案は以下です。実現可能有無などを検討した上で、設計書をまとめてください。
1. 理想的な月間レポートの構成（Slack/ミーティング用）
単なる数字の羅列ではなく、**「何が起きたか」「なぜ起きたか」「次どうするか」**がひと目でわかる構成が理想的です。

サマリー（全体像）:
チャンネル全体の総視聴数、総インプレッション数、新規登録者数。
前月比（％）を併記し、成長トレンドを可視化。
動画別ランキング（Top 3 / Bottom 3）:
インプレッション数順: 「露出」の強さを確認。
クリック率（CTR）順: 「サムネイル・タイトル」の引きの強さを確認。
平均視聴維持率順: 「コンテンツの満足度」を確認。
視聴者分析:
リピーター vs 新規視聴者の比率: チャンネルの「ファン化」が進んでいるか、外部への「拡散」が起きているかを判断。
2. API連携機能に組み込むべき「ベストな追加機能」
分析をより深く、かつ自動化するために、以下の機能を組み込むことを強くおすすめします。

① 「初動24時間・7日間」の比較分析
公開から一定期間（例：最初の24時間）のパフォーマンスを過去の動画平均と比較する機能です。

メリット: 月末に振り返るだけでなく、「この動画は平均より初動が良いから、さらにプッシュしよう」といった迅速な判断が可能になります。
② トラフィックソース別のパフォーマンス特定
視聴者が「関連動画」から来たのか、「YouTube検索」から来たのかを自動判別します。

メリット: 「検索に強い動画」と「おすすめに乗りやすい動画」を分けることで、チーム内での企画の狙い（SEO狙いかバズ狙いか）が明確になります。
③ 視聴維持率の「離脱ポイント」自動抽出
動画のどの地点で大きく視聴者が離脱したか、または繰り返し再生されたかを特定します。

メリット: ミーティングで「1分30秒あたりの説明が長すぎて離脱されている」といった、具体的な編集の改善案を議論しやすくなります。
④ コメントの「頻出キーワード」と感情分析
視聴者のコメントから、ポジティブな反応や質問が多いトピックを自動でまとめます。

メリット: 数値（定量）だけでなく、視聴者の生の声（定性）をチームで共有でき、次回の動画のQ&A企画や改善に直結します。