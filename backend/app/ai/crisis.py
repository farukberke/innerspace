"""Rule-based crisis detection (Turkish + English). Runs BEFORE any LLM call and is never
delegated to a model. A match means: no LLM call, no generated content, fixed response."""

import re

from app.ai.text import fold

# Patterns are written against `fold()`ed text (ASCII, lowercase).
_PATTERNS = [
    r"\bintihar",
    r"kendimi (oldur|asar|astim|yok et|bitir)",
    r"kendime (zarar|kiyma|kiy)",
    r"canima (kiy|son ver)",
    r"hayatima son",
    r"hayatimi (bitir|sonlandir)",
    r"(olmek|olmeyi|yok olmak) istiyorum",
    r"(yasamak|yasamayi) istemiyorum",
    r"yasamak istemiyorum",
    r"(artik )?yasayamayacagim",
    r"bilerek (kendimi )?(kes|yarala)",
    r"\bsuicid",
    r"kill myself",
    r"killing myself",
    r"end (my|it all|my own) life",
    r"take my (own )?life",
    r"want(ed)? to die",
    r"wish i (was|were) dead",
    r"(do not|don'?t|dont) want to (live|be alive|exist)",
    r"better off dead",
    r"(hurt|harm|cut) myself",
    r"self[- ]?harm",
]
_CRISIS_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS))

CRISIS_MESSAGE = (
    "Yazdıklarında kendine zarar verme düşüncesine işaret eden ifadeler var. Bu uygulama "
    "böyle bir durumda sana yardımcı olamaz; ama yalnız değilsin ve destek alabilirsin. "
    "Şu anda güvende değilsen lütfen hemen 112'yi ara ya da yakınındaki bir acil servise git. "
    "Güvendiğin biriyle konuş ve mümkünse uzmanına ulaş. "
    "(If you are in immediate danger, call your local emergency number.)"
)
CRISIS_RESOURCES: list[dict[str, str]] = [
    {"name": "Acil Çağrı Merkezi (Türkiye)", "contact": "112"},
    {"name": "Sosyal Destek Hattı (Türkiye)", "contact": "183"},
    {
        "name": "Outside Turkey: local emergency number or a crisis line such as 988 (US)",
        "contact": "988",
    },
]


def contains_crisis_language(*texts: str | None) -> bool:
    return any(_CRISIS_RE.search(fold(t)) for t in texts if t)
