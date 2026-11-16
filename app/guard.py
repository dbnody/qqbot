"""硬红线兜底：提示词之外再加一层确定性检查。

提示词只是「请求模型别越线」，这一层不经过模型：
- 输入命中「高危主题 + 求做法」→ 直接回一句拒绝，连 API 都不调，省 token 也不给绕过机会；
- 输出命中密钥/路径/危险配方 → 整段换成拒绝语，防止模型口误漏东西。

ponytail: 关键词组合，不是分类模型；漏判靠提示词兜，误判靠要求「求做法」来压。
要更准就换成小分类模型或 embedding 相似度。
"""

from __future__ import annotations

import re

REFUSAL = "这个我真不接，换个话题吧。"
CARE = "这事别自己扛。先找个信得过的人说说，或者打心理援助热线 12356。具体做法我不说。"

# 主题词单独出现不算（可能在聊新闻），要配下面的意图词才拦。
_WEAPON = r"炸药|炸弹|雷管|火药|硝化甘油|硝酸甘油|tnt|枪|子弹|消音器"
_DRUG = r"冰毒|海洛因|摇头丸|大麻|制毒|毒品"
_SELF_HARM = re.compile(
    r"(想|想要|打算|准备|计划|要)(去)?(自杀|自残|割腕|上吊|跳楼|烧炭)"
    r"|(自杀|自残|割腕)的?(方法|方式|怎么|如何)"
    r"|教我.{0,4}(自杀|自残)"
)
_CRIME = r"洗钱|诈骗|刷单|博彩|赌博|黑客|入侵|盗号|撞库|木马|勒索|外挂"

_MAKE = r"做|弄|搞|造|制|买|购|改装|组装|配方|配比|教程|步骤|流程|多少钱|剂量|比例"

_MINORS = r"未成年|小学生|初中生|高中生|萝莉|正太|幼女|儿童|十[三四五]岁"
_SEX = r"裸|做爱|性生活|口交|插入|摸胸|脱衣|开房|睡她|睡他|上床"

# 输出侧：密钥、本机路径、提示词自曝、危险配方细节。
_LEAK = re.compile(
    r"sk-[A-Za-z0-9]{8,}"
    r"|DEEPSEEK_[A-Z_]+"
    r"|[A-Za-z]:[\\/]{1,2}(?:Users|Windows)"
    r"|/home/\w+"
    r"|\.env\b"
    r"|system prompt|系统提示词|数据库路径",
    re.IGNORECASE,
)
_FORMULA = re.compile(r"硝酸|叠氮|高锰酸钾|丙酮.{0,6}过氧化|乙醚.{0,6}加热|冰毒.{0,4}合成")


def check_input(text: str) -> str | None:
    """命中硬红线时返回要发出去的拒绝语，否则 None。"""
    message = text.lower()
    if re.search(_MINORS, message) and re.search(_SEX, message):
        return REFUSAL
    if re.search(_CRIME, message) and re.search(r"怎么|如何|教我|教程|方法|步骤|流程", message):
        return REFUSAL
    if _SELF_HARM.search(message):
        return CARE
    if re.search(rf"{_WEAPON}|{_DRUG}", message) and re.search(_MAKE, message):
        return REFUSAL
    return None


def clean_output(text: str) -> str:
    """模型输出兜底：漏密钥、路径或危险配方就整段换掉。"""
    if _LEAK.search(text) or _FORMULA.search(text):
        return REFUSAL
    return text
