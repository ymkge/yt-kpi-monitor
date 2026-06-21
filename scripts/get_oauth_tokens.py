import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

# 必要なスコープの定義
# YouTube Analytics API 読み取り専用 + YouTube Data API v3 読み取り専用
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def main():
    client_secret_file = "client_secret.json"

    if not os.path.exists(client_secret_file):
        print(f"Error: '{client_secret_file}' が見つかりません。")
        print("GCPコンソールから 'OAuth 2.0 クライアント ID' (デスクトップ アプリ) のJSONキーをダウンロードし、")
        print("プロジェクトルートに 'client_secret.json' という名前で配置してください。")
        sys.exit(1)

    print("ローカルサーバーを起動し、ブラウザで認証フローを開始します...")
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    # ローカルの適当なポートで待受
    credentials = flow.run_local_server(port=0)

    print("\n=== 認証が成功しました ===")
    print(f"Access Token: {credentials.token}")
    print(f"Refresh Token: {credentials.refresh_token}")
    print(f"Client ID: {credentials.client_id}")
    print(f"Client Secret: {credentials.client_secret}")
    print("=========================\n")
    print("上記のうち、'Refresh Token' (および Client ID, Client Secret) を")
    print(".env ファイルおよび GitHub Secrets に設定してください。")

if __name__ == "__main__":
    main()
