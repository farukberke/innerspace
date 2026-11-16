import unicodedata

# Common Cyrillic look-alikes (lowercase) -> Latin, so they cannot be used to dodge the rules.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "і": "i",
        "ј": "j",
        "у": "y",
        "к": "k",
        "м": "m",
        "т": "t",
        "н": "h",
        "в": "b",
        "ѕ": "s",
    }
)


def fold(text: str) -> str:
    """Normalise text for rule matching: lowercase, strip accents and invisible format
    characters (zero-width, soft hyphen, BOM...), map Turkish dotless i and Cyrillic
    look-alikes. Rules are then written in plain ASCII.

    "ÖLMEK", "ölmek" and "olmek" all fold to "olmek"; "te​shis" folds to "teshis".
    """
    decomposed = unicodedata.normalize("NFKD", text.replace("İ", "I").replace("ı", "i"))
    kept = "".join(
        ch
        for ch in decomposed
        if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf"
    )
    return " ".join(kept.lower().translate(_HOMOGLYPHS).split())
