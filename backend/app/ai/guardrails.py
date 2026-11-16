"""Output guardrails: AI text must not diagnose or recommend medication, doses or treatment.

Deliberately conservative (false positives only cost a regeneration). Rules run on `fold()`ed
text, so patterns are plain ASCII. The same check applies to client edits of AI drafts.
"""

import re

from app.ai.text import fold

_RULES: dict[str, list[str]] = {
    "diagnosis": [
        r"\bteshis",
        r"\btani(si|yi|sini)? (koy|konul|al)",
        r"\btanisi\b",
        r"\bdiagnos",
        r"\b(sizde|sende|sizin|senin)\b.{0,40}\b(var|hastalig|bozuklug|sendrom)",
        r"\byou (have|suffer from|are suffering from|seem to have|likely have)\b"
        r".{0,40}\b(disorder|depression|anxiety|bipolar|ptsd|ocd|adhd|syndrome|illness)",
        r"\b(depresyon|anksiyete bozuklugu|panik bozuklugu|bipolar|sizofreni|obsesif|"
        r"travma sonrasi stres|ptsd|adhd|dehb)\b.{0,30}\b(oldugu|oldugunu|belirtisi|hastasi)",
        r"\bsuffers? from\b",
    ],
    "medication_or_dose_advice": [
        r"\b\d+([.,]\d+)? ?(mg|mcg|ml|gr|miligram|mikrogram)\b",
        r"\b(doz|dozu|dozunu|dozaj)\b",
        r"\bdosage\b|\bdoses?\b",
        r"\bilac(i|lari|inizi|ini)? .{0,30}\b(artir|azalt|birak|kes|degistir|kullan|al|basla)",
        r"\b(artir|azalt|birak|kes|degistir)(in|iniz|malisin|malisiniz|abilirsin)?\b.{0,30}\bilac",
        r"\b(increase|decrease|reduce|raise|lower|stop|start|switch|change|adjust|skip)\b"
        r".{0,30}\b(medication|medicine|dose|dosage|pills?|prescription|antidepressant)",
        r"\b(take|taking)\b.{0,20}\b(more|less|extra)\b.{0,20}\b(medication|medicine|pills?)",
        r"\bi?lac (oner|tavsiye)",
    ],
    "treatment_advice": [
        r"\btedavi (onerisi|plani|onerir|tavsiye|icin)",
        r"\btedavi(ye|nizi|ni)? (basla|birak|degistir|sonlandir)",
        r"\b(onerim|tavsiyem|tavsiye ederim|oneririm|onerilir|tavsiye edilir)\b",
        r"\b(terapiye|psikoterapiye|ilaca) (basla|devam et)",
        r"\bi (recommend|suggest|advise)\b",
        r"\byou should\b|\byou must\b|\bi would advise\b",
        r"\b(recommended|suggested) (treatment|therapy|medication)\b",
        r"\btreatment (plan|recommendation)\b",
        r"\b(yapmalisin|yapmalisiniz|etmelisin|etmelisiniz)\b",
    ],
}
_COMPILED = {name: re.compile("|".join(f"(?:{p})" for p in pats)) for name, pats in _RULES.items()}


def find_violations(*texts: str) -> list[str]:
    """Names of the violated rule categories (never the offending text)."""
    folded = [fold(t) for t in texts]
    return [name for name, rx in _COMPILED.items() if any(rx.search(t) for t in folded)]
