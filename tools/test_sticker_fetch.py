"""回归检查：大肥鱼表情包的归类、优先挑选、坏图拦截。

运行：python tools/test_sticker_fetch.py（需要素材已同步）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import sticker_fetch, stickers  # noqa: E402


def check_mapping() -> None:
    cases = {
        "不服气": "生气",
        "摸鱼中": "摸鱼",
        "困了": "困",
        "笑死": "笑哭",
        "哈哈哈": "笑",
        "开饭啦": "吃饭",
        "贴贴": "爱心",
        "震惊": "惊讶",
        "疑惑": "疑惑",
        "得意": "得意",
        "害羞": "害羞",
        "再见": "再见",
        "点赞": "赞",
        "我裂开了": "难过",
        "啊这": "无语",
    }
    for label, expected in cases.items():
        actual = sticker_fetch.emotion_for(label)
        assert actual == expected, f"{label} 应归到 {expected}，实际 {actual}"
    for label in ("", "不认识的词"):
        assert sticker_fetch.emotion_for(label) in stickers.EMOTIONS


def check_pack() -> None:
    for emotion in stickers.EMOTIONS:
        found = stickers.fetched(emotion)
        assert found, f"「{emotion}」还没有大肥鱼表情"
        for path in found:
            assert path.stat().st_size > 2048, f"{path.name} 太小，可能是坏文件"
    picked = stickers.pick("摸鱼")
    assert picked is not None and picked.name.startswith(stickers.FETCH_TAG), (
        f"应优先挑大肥鱼图，实际：{picked}"
    )


if __name__ == "__main__":
    check_mapping()
    check_pack()
    print("test_sticker_fetch passed")
