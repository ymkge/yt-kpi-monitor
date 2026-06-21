# 開発・実装ルール

## セキュリティ規約
- **認証情報の管理**:
  - サービスアカウントキーや各種APIトークン（Slack Webhook URL, Gemini API Key, YouTube API Key）は、絶対にコード内に直書きしない。
  - すべて環境変数（GitHub Secrets）から読み込む構成にすること。
  - セキュリティリスクを最小化するため、SSH鍵による認証ではなく、Personal Access Token (PAT) やサービスアカウントによる適切なスコープ管理を行う。

## SQLコーディング規約 (BigQuery)
- **カンマの配置**: 列定義やSELECT文における**「前カンマ（leading commas）」は一切禁止**。必ず後ろカンマ（trailing commas）で記述すること。
- **予約語**: SQL of keywords (SELECT, FROM, WHERE, GROUP BY など) はすべて大文字で統一すること。
- **データ型**: 日時は `TIMESTAMP` または `DATETIME` 型を適切に使い分け、タイムゾーン（アジア/東京）を意識した設計にすること。
