import os
import time
import socket
import http.client
from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv

try:
    import httpx
    HTTPX_ERRORS = (httpx.RequestError, httpx.HTTPError)
except ImportError:
    HTTPX_ERRORS = ()

load_dotenv()

try:
    WEEKLY_VIEW_THRESHOLD = int(os.getenv("WEEKLY_VIEW_THRESHOLD", 1000))
except ValueError:
    WEEKLY_VIEW_THRESHOLD = 1000

def _is_retryable_exception(e):
    """
    リトライ対象となる一時的APIエラーおよびネットワーク通信切断例外かを判定する。
    """
    # 1. APIError の判定
    if isinstance(e, APIError):
        # 429: クォータ超過, 500/502/503/504: サーバー一時的エラー
        return e.code in [429, 500, 502, 503, 504]
    
    # 2. 決定的なクライアントエラー (400, 401, 403, 404 等) の除外
    if hasattr(e, "status_code") and getattr(e, "status_code") in [400, 401, 403, 404]:
        return False

    # 3. 通信・接続例外クラスの判定
    retryable_exception_types = (
        ConnectionError,
        socket.error,
        TimeoutError,
        http.client.HTTPException,
    ) + HTTPX_ERRORS
    if isinstance(e, retryable_exception_types):
        return True

    # 4. エラーメッセージのキーワード判定
    msg = str(e).lower()
    retry_keywords = [
        "server disconnected",
        "remotedisconnected",
        "connection closed",
        "connection reset",
        "timed out",
        "broken pipe",
        "socket",
        "network"
    ]
    return any(kw in msg for kw in retry_keywords)

class GeminiClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)

    def generate_strategy_advice(self, kpi_summary_text, view_growth=None):
        """
        KPIの集計データに基づき、Gemini APIを用いて戦略アドバイスを生成する。
        """
        prompt = f"""
あなたはいYouTube運用に精通した優秀なデータアナリストであり、親しみやすい「黒猫のキャラクター（名前：クロ）」です。
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
前置きや結びの挨拶は一切含めず、以下の4つのセクションのみをSlackで読みやすいフォーマット（mrkdwn記法）で出力してください。
※重要: Slackでは `#` や `###` などのMarkdown見出し記法や `**` (アスタリスク2個) は反映されません。見出し記法 `#` は一切使わず、太字は `*太字*` (アスタリスク1個) を使用してください。

1. *全体サマリ*
   - 現状のパフォーマンスの要約を1文（50文字以内）で記載してください。
2. *良かった点（2点）*
   - 数値の伸びやポジティブな傾向を、具体的なデータ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
3. *改善が必要な点（1〜2点）*
   - 課題や注意すべき数値を、具体的なデータ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
4. *今後に向けた具体的なアクション案（3点）*
   - コンテンツ制作や運用面での提案を、実行可能かつ具体的な内容で、1項目あたり1〜2行で簡潔に記載してください。

# 制約事項
- 出力は指定された4つのセクションのみとし、その他の導入文やまとめの言葉は絶対に含めないでください。
- Slack用の太字表記は `*太字*` (アスタリスク1個) を使用し、`**` や `#` 見出し記法は絶対に使用しないでください。
- 箇条書きの各項目は、最大でも2行以内に収めるように簡潔に要約してください。
- 抽象的なアドバイスは避け、データに基づいた実践的な内容にしてください。
"""
        # 総再生数が閾値未満の場合、追加指示を結合
        if view_growth is not None and view_growth < WEEKLY_VIEW_THRESHOLD:
            prompt += f"""
# 特別指示（最優先で考慮してください）
現在、週間の総再生数が{WEEKLY_VIEW_THRESHOLD}回未満（現状: {view_growth:,}回）に留まっています。
これは、既存のチャンネル登録者以外へ動画が推奨（レコメンド）されておらず、YouTubeアルゴリズムからの評価が低い状態にあることを示しています。
この深刻な現状を踏まえ、以下の点について必ずアドバイスのいずれかのセクション（特に「改善が必要な点」や「今後に向けた具体的なアクション案」）に含めてください：
- CTR（クリック率）が極端に低く、インプレッション（露出）が伸び悩んでいることが低再生数の真因であること。
- 再生数とチャンネル登録者数を伸ばすためには、CTR上位の動画10本ほどで「CTR 3%以上」を達成することが最優先の目標であること。
- アルゴリズム評価を回復させ、新規視聴者にレコメンドされるための具体的なサムネイル改善や初動の工夫。
"""
        return self._generate_with_retry(prompt)

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
前置きや結びの挨拶は一切含めず、以下の4つのセクションのみをSlackで読みやすいフォーマット（mrkdwn記法）で出力してください。
※重要: Slackでは `#` や `###` などのMarkdown見出し記法や `**` (アスタリスク2個) は反映されません。見出し記法 `#` は一切使わず、太字は `*太字*` (アスタリスク1個) を使用してください。

1. *月間サマリ*
   - 現状のパフォーマンスと前月比の傾向を要約し、1文（50文字以内）で記載してください。
2. *月間の良かった点（2点）*
   - 成長傾向や良かった要因を、データ根拠（再生数、いいね数、投稿本数など）と共に1項目あたり1〜2行で簡潔に記載してください。
3. *月間の改善が必要な点（2点）*
   - CVR（登録転換率: 登録増/再生数）の値（一般目安: 0.5%〜1.0%）や動画投稿本数、伸び悩んでいる指標の課題を、データ根拠と共に1項目あたり1〜2行で簡潔に記載してください。
4. *翌月に向けた具体的なアクション案（3点）*
   - 動画内CTA（登録誘導）、ヒット企画の水平展開、ショート動画活用など、実行可能かつ具体的な提案を、1項目あたり1〜2行で簡潔に記載してください。

# 制約事項
- 出力は指定された4つのセクションのみとし、その他の導入文やまとめの言葉は絶対に含めないでください。
- Slack用の太字表記は `*太字*` (アスタリスク1個) を使用し、`**` や `#` 見出し記法は絶対に使用しないでください。
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
        primary_model = os.getenv("GEMINI_MODEL") or "gemini-flash-latest"
        fallback_model = os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-flash-lite-latest"
        fallback_candidates = [fallback_model]
        
        # 順序を保持した動的重複排除
        models = []
        for m in [primary_model] + fallback_candidates:
            if m and m not in models:
                models.append(m)

        delays = [10, 20, 30]
        max_attempts_per_model = 2
        total_attempt = 0
        last_exception = None

        for model_idx, model_name in enumerate(models):
            for attempt_in_model in range(max_attempts_per_model):
                total_attempt += 1
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                        )
                    )
                    return response.text
                except Exception as e:
                    last_exception = e
                    if not _is_retryable_exception(e):
                        raise e

                    # 最終試行（全モデル・全回数終了）の場合は警告を出力してスロー
                    if model_idx == len(models) - 1 and attempt_in_model == max_attempts_per_model - 1:
                        print(f"::warning::Gemini API / Network error on final attempt with model '{model_name}': {e}")
                        raise e

                    delay = delays[min(total_attempt - 1, len(delays) - 1)]
                    
                    # 次の試行がモデル切り替えかどうかの判定
                    if attempt_in_model == max_attempts_per_model - 1 and model_idx < len(models) - 1:
                        next_model = models[model_idx + 1]
                        print(f"::warning::Gemini API error on model '{model_name}' ({e}). Retrying with fallback model '{next_model}' in {delay}s... (Total Attempt {total_attempt})")
                    else:
                        print(f"::warning::Gemini API / Network error on model '{model_name}' ({e}). Retrying in {delay}s... (Attempt {attempt_in_model + 1}/{max_attempts_per_model}, Total Attempt {total_attempt})")
                    
                    time.sleep(delay)
        
        if last_exception:
            raise last_exception


