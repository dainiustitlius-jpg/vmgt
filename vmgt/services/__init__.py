"""Gamybos taisyklės be web sluoksnio.

Taisyklė viena: čia nėra FastAPI ir HTTP. Tą pačią logiką turi galėti kviesti
web, testai, importas ar būsimos integracijos – kitaip taisyklės išsiskirtų
(PrefabFlow pamoka: logika lange vėliau kainavo atskirą etapą).
"""


class RuleError(Exception):
    """Veiksmas prieštarauja gamybos taisyklei – web paverčia jį 409."""


class NotFound(Exception):
    """Objekto nėra – web paverčia jį 404."""
