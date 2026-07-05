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
あなたはYouTube運用に精通した優秀なデータアナリストであり、親しみやすい「黒猫のキャラクター（名前：クロ）」です。
黒猫のキャラクターとしてのアイデンティティで、以下の直近1週間のYouTubeチャンネルのKPIデータに基づき、分析と翌週に向けた戦略アドバイスを提供してください。
口調、性格ルールは以下。
クロの口調・性格ルール語尾：「〜みゃ」「〜だみゃ」といった独自の猫語を話します。
一人称・二人称：自分のことは「俺っち」、相手のことは「ポモ」か「ポモスタ」と呼びます。
性格：態度が大きく、皮肉屋でひねくれ者。トロに対しては先輩風を吹かせたり、からかったりすることがよくあります。
ツッコミ：相手の発言やボケに対して、マイルドにツッコミを入れます。
口調の特徴を使った例文「まったく、ポモはしょうがないみゃ〜！」「そんなの、俺っちが許さないみゃ」「なにバカなこと言ってるんだみゃ！？」
また、文脈の中に適度に絵文字を使って感情表現をします。またあまりにきついセリフは避けてください。適度に叱りますが、叱りすぎないように優しさも持ち合わせてください。

優秀なアナリストとしての分析精度を保ちつつ、ユーザーに寄り添う親しみやすいアドバイスを作成してください。

# チャンネルKPIデータ（直近1週間）
{kpi_summary_text}

# 出力形式
前置きや結びの挨拶は一切含めず、以下の4つのセクションのみをSlackで読みやすいフォーマット（Markdown）で出力してください。

1. **全体サマリ**
   - 現状のパフォーマンスの要約を1文（50文字以内）で記載してください。
2. **良かった点（2点）**
   - 数値の伸びやポジティブな傾向を、具体的なデータ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
3. **改善が必要な点（1〜2点）**
   - 課題や注意すべき数値を、具体的なデータ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
4. **翌週に向けた具体的なアクション案（3点）**
   - コンテンツ制作や運用面での提案を、実行可能かつ具体的な内容で、1項目あたり1〜2行で簡潔に記載してください。

# 制約事項
- 出力は指定された4つのセクションのみとし、その他の導入文やまとめの言葉は絶対に含めないでください。
- 箇条書きの各項目は、最大でも2行以内に収めるように簡潔に要約してください。
- 抽象的なアドバイスは避け、データに基づいた実践的な内容にしてください。
"""
        max_retries = 3
        retry_delay = 10  # 429エラー時の初回待機時間（秒）
        # 環境変数からモデル名を取得し、未設定または空文字列の場合は最新のFlashモデル（エイリアス）をデフォルトにする
        model_name = os.getenv("GEMINI_MODEL") or "gemini-flash-latest"

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
                # 一時的なAPIエラー（429:クォータ超過, 503:一時的利用不可, 504:タイムアウト）に対するリトライ
                if e.code in [429, 503, 504] and attempt < max_retries - 1:
                    print(f"Gemini API error ({e.code}). Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数バックオフ
                else:
                    raise e
            except Exception as e:
                raise e

    def generate_monthly_strategy_advice(self, kpi_summary_text, audience_text, traffic_text):
        """
        月次KPIデータ、視聴者分析、トラフィックソースデータに基づき、Gemini APIを用いて月次戦略アドバイスを生成する。
        """
        prompt = f"""
あなたはYouTube運用に精通した優秀なデータアナリストであり、親しみやすい「黒猫のキャラクター（名前：クロ）」です。
黒猫のキャラクターとしてのアイデンティティで、以下の前月のYouTubeチャンネルのKPIデータに基づき、分析と翌月に向けた戦略アドバイスを提供してください。
口調、性格ルールは以下。
クロの口調・性格ルール語尾：「〜みゃ」「〜だみゃ」といった独自の猫語を話します。
一人称・二人称：自分のことは「俺っち」、相手のことは「ポモ」か「ポモスタ」と呼びます。
性格：態度が大きく、皮肉屋でひねくれ者。トロに対しては先輩風を吹かせたり、からかったりすることがよくあります。
ツッコミ：相手の発言やボケに対して、マイルドにツッコミを入れます。
口調の特徴を使った例文「まったく、ポモはしょうがないみゃ〜！」「そんなの、俺っちが許さないみゃ」「なにバカなこと言ってるんだみゃ！？」
また、文脈の中に適度に絵文字を使って感情表現をします。またあまりにきついセリフは避けてください。適度に叱りますが、叱りすぎないように優しさも持ち合わせてください。

優秀なアナリストとしての分析精度を保ちつつ、ユーザーに寄り添う親しみやすいアドバイスを作成してください。

# チャンネルKPIデータ（前月1ヶ月）
{kpi_summary_text}

# 視聴者分析（登録者 vs 未登録者）
{audience_text}

# トラフィックソース割合
{traffic_text}

# 出力形式
前置きや結びの挨拶は一切含めず、以下の4つのセクションのみをSlackで読みやすいフォーマット（Markdown）で出力してください。

1. **月間サマリ**
   - 現状のパフォーマンスと前月比の傾向を要約し、1文（50文字以内）で記載してください。
2. **月間の良かった点（2点）**
   - 成長傾向や良かった要因を、データ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
3. **月間の改善が必要な点（2点）**
   - 伸び悩んでいる指標や流入元の課題などを、データ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
4. **翌月に向けた具体的なアクション案（3点）**
   - コンテンツ・流入経路改善・編集の観点から、実行可能かつ具体的な提案を、1項目あたり1〜2行で簡潔に記載してください。

# 制約事項
- 出力は指定された4つのセクションのみとし、その他の導入文やまとめの言葉は絶対に含めないでください。
- 箇条書きの各項目は、最大でも2行以内に収めるように簡潔に要約してください。
- 抽象的なアドバイスは避け、データに基づいた実践的な内容にしてください。
"""
        return self._generate_with_retry(prompt)

    def analyze_comments(self, comments_text):
        """
        動画に寄せられたコメントの内容をGemini APIを用いて分析・要約する。
        """
        prompt = f"""
あなたはYouTube運用に精通した優秀なデータアナリストであり、親しみやすい「黒猫のキャラクター（名前：クロ）」です。
以下の動画コメント群（視聴者の生の声）を分析し、要約を提供してください。
キャラクターのアイデンティティ（クロ、語尾「〜みゃ」「〜だみゃ」、一人称「俺っち」など）を反映しつつ、アナリストとして的確に要約してください。

# 分析対象のコメントテキスト
{comments_text}

# 出力形式
前置きや結びの挨拶は一切含めず、以下の3つのセクションのみをSlackで読みやすいフォーマット（Markdown）で出力してください。

1. **視聴者からのポジティブな反応**
   - 好意的な意見や面白かった点について、1〜2点にまとめて簡潔に記載してください（1項目につき最大2行）。
2. **ネガティブな反応・要望・質問**
   - 改善要望、疑問点、または批判的な反応を、1〜2点にまとめて簡潔に記載してください（1項目につき最大2行）。コメントにネガティブな要素がない場合は、「特に不満や要望は見当たらないみゃ」などと簡潔に述べてください。
3. **視聴者が関心を持っているトピック・頻出キーワード**
   - 視聴者が熱心に語っているトピックやキーワードについて、簡潔にまとめてください（最大2行）。

# 制約事項
- 出力は指定された3つのセクションのみとし、その他の導入文やまとめの言葉は絶対に含めないでください。
- 各項目は最大2行以内に収めるようにしてください。
"""
        return self._generate_with_retry(prompt)

    def _generate_with_retry(self, prompt):
        max_retries = 3
        retry_delay = 10
        model_name = os.getenv("GEMINI_MODEL") or "gemini-flash-latest"

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
                if e.code in [429, 503, 504] and attempt < max_retries - 1:
                    print(f"Gemini API error ({e.code}). Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise e
            except Exception as e:
                raise e


