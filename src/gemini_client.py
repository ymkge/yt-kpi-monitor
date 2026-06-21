import os
import time
from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv

load_dotenv()

class GeminiClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)

    def generate_strategy_advice(self, kpi_summary_text):
        """
        KPIの集計データに基づき、Gemini APIを用いて戦略アドバイスを生成する。
        """
        prompt = f"""
あなたはYouTube運用に精通したデータアナリスト兼戦略コンサルタントです。
以下の直近1週間のYouTubeチャンネルのKPIデータに基づき、分析と翌週に向けた戦略アドバイスを提供してください。

# チャンネルKPIデータ（直近1週間）
{kpi_summary_text}

# 出力形式
1. **全体サマリ**: 現状のパフォーマンスを1文で。
2. **良かった点**: 数値の伸びやポジティブな傾向を2-3点。
3. **改善が必要な点**: 課題や注意すべき数値を1-2点。
4. **翌週に向けた具体的なアクション案**: コンテンツ制作や運用面での提案を3点。

回答は簡潔かつデータに基づいた具体的な内容にしてください。
"""
        max_retries = 3
        retry_delay = 10  # 429エラー時の初回待機時間（秒）
        # 環境変数からモデル名を取得し、未設定の場合は推奨版のgemini-3.5-flashをデフォルトにする
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                    )
                )
                return response.text
            except APIError as e:
                # 429 RESOURCE_EXHAUSTED のエラーハンドリング
                if e.code == 429 and attempt < max_retries - 1:
                    print(f"Gemini API rate limit exceeded (429). Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数バックオフ
                else:
                    raise e
            except Exception as e:
                raise e

