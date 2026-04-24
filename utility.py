"""
utility.py

Utility condivise del progetto.

Nota:
- il logger NON sta qui
- il logger sta in logger.py
- qui teniamo solo funzioni helper riutilizzabili
"""


def mask_token(token: str | None, left: int = 6, right: int = 4) -> str:
    """
    Maschera token o stringhe sensibili nei log.

    Esempio:
    ABCDEF1234567890 -> ABCDEF...7890
    """
    if not token:
        return "<none>"

    token = str(token)

    if len(token) <= left + right:
        return token

    return f"{token[:left]}...{token[-right:]}"