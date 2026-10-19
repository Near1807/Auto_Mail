"""Garde contre la cause de la page blanche de fin d'envoi (v1.0.0).

Un effet React écrit ``useEffect(() => expression, …)`` renvoie la valeur de l'expression ;
React la prend pour une fonction de nettoyage. ``scrollIntoView()`` renvoyant une Promise
dans le WebView2 récent, React appelait cette Promise → « TypeError: p is not a function ».
Les effets doivent donc toujours avoir un corps entre accolades.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
SHORT_EFFECT = re.compile(r"use(Layout)?Effect\(\s*(async\s*)?\(\s*\)\s*=>\s*(?![\s{])")


def test_effects_never_return_an_expression():
    offenders = []
    for file in SRC.rglob("*.tsx"):
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if SHORT_EFFECT.search(line):
                offenders.append(f"{file.relative_to(SRC)}:{number}: {line.strip()}")
    assert not offenders, "Effets à écrire avec un corps { … } :\n" + "\n".join(offenders)
