import unicodedata


def fold(text: str) -> str:
    """Lowercase, strip accents and map Turkish dotless i, so rules are written in plain ASCII.

    "ÖLMEK", "ölmek" and "olmek" all fold to "olmek"; "İntihar" and "INTIHAR" to "intihar".
    """
    decomposed = unicodedata.normalize("NFKD", text.replace("İ", "I").replace("ı", "i"))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())
