import os
import re
from typing import Dict, Any, Optional

class KnowledgeManager:
    """
    config/knowledge/ ディレクトリ配下のナレッジファイル（.md, .txt）を自動検知・パースし、
    チャンネルの登録者数などの条件に合致したアドバイス前提知識を抽出するクラス。
    """
    def __init__(self, knowledge_dir: Optional[str] = None):
        if knowledge_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            knowledge_dir = os.path.join(base_dir, "config", "knowledge")
        self.knowledge_dir = knowledge_dir

    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """
        標準ライブラリのみでYAML形式のフロントマターをパースする。
        """
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return {}, content.strip()

        yaml_text = match.group(1)
        body = match.group(2).strip()
        metadata = {}

        for line in yaml_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()

                if val.isdigit():
                    val = int(val)
                elif val.lower() in ("true", "false"):
                    val = val.lower() == "true"
                else:
                    val = val.strip("'\"")

                metadata[key] = val

        return metadata, body

    def get_relevant_knowledge(self, current_subscribers: Optional[int] = None, max_length: int = 3000) -> str:
        """
        現在の登録者数に合致するナレッジテキストを取得・整形して返す。
        """
        if not os.path.exists(self.knowledge_dir):
            return ""

        knowledge_items = []

        try:
            filenames = sorted([
                f for f in os.listdir(self.knowledge_dir)
                if not f.startswith(".") and (f.endswith(".md") or f.endswith(".txt"))
            ])
            for filename in filenames:
                filepath = os.path.join(self.knowledge_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    print(f"::warning::Failed to read knowledge file {filename}: {e}")
                    continue

                metadata, body = self._parse_frontmatter(content)

                # 登録者数フィルタリング
                if current_subscribers is not None:
                    min_sub = metadata.get("min_subscribers")
                    max_sub = metadata.get("max_subscribers")

                    if min_sub is not None:
                        try:
                            if current_subscribers < int(min_sub):
                                continue
                        except (ValueError, TypeError):
                            pass

                    if max_sub is not None:
                        try:
                            if current_subscribers > int(max_sub):
                                continue
                        except (ValueError, TypeError):
                            pass

                title = metadata.get("title", filename)
                knowledge_items.append(f"■ 【専門ナレッジ】{title}\n{body}")

        except Exception as e:
            print(f"::warning::Error scanning knowledge directory: {e}")
            return ""

        if not knowledge_items:
            return ""

        combined_text = "\n\n".join(knowledge_items)
        if len(combined_text) > max_length:
            combined_text = combined_text[:max_length] + "\n...(以降のナレッジは省略)"

        return combined_text
