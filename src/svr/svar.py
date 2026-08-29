"""Le vecteur autorégressif structurel, et l'identification récursive que le travail emploie.

Un **VAR** relie chaque variable à ses propres valeurs passées et à celles de toutes les autres. Il
décrit les corrélations, mais pas les causes : ses résidus bougent ensemble, et rien ne dit lequel
pousse l'autre. Un **SVAR** ajoute une hypothèse qui sépare les chocs, et l'hypothèse retenue ici est
celle de Christiano, Eichenbaum et Evans (1999) : les variables sont rangées dans un ordre, et une
variable ne réagit dans le mois à un choc que si elle vient après lui dans cet ordre.

Le code R de 2021 écrit cette hypothèse en donnant à `SVAR` une matrice `Amat` triangulaire
inférieure dont toutes les cases sous la diagonale sont libres. Une telle matrice n'est rien d'autre
que l'inverse du facteur de Cholesky de la covariance des résidus, la décomposition qui écrit une
matrice de covariance comme le produit d'une matrice triangulaire par sa transposée. Ce module
l'obtient donc directement par Cholesky, et un test vérifie l'identité.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR


@dataclass
class Structurel:
    """Un SVAR estimé : le modèle réduit, le facteur de Cholesky, et de quoi tirer les réponses."""

    nom: str
    variables: list[str]
    retards: int
    observations: int
    ajuste: object
    facteur: np.ndarray            # le facteur de Cholesky de la covariance des résidus

    @property
    def matrice_a(self) -> np.ndarray:
        """La matrice `Amat` du code de 2021 : l'inverse du facteur, triangulaire inférieure."""
        return np.linalg.inv(self.facteur)


def estimer(donnees: pd.DataFrame, retards: int, nom: str = "") -> Structurel:
    """Le VAR à constante, puis le facteur de Cholesky de la covariance de ses résidus."""
    ajuste = VAR(donnees).fit(retards, trend="c")
    facteur = np.linalg.cholesky(np.asarray(ajuste.sigma_u))
    return Structurel(nom or "svar", list(donnees.columns), retards, int(ajuste.nobs),
                      ajuste, facteur)


def selection_retards(donnees: pd.DataFrame, maximum: int = 10) -> pd.DataFrame:
    """Les quatre critères d'information, comme `VARselect` en R."""
    resultat = VAR(donnees).select_order(maxlags=maximum, trend="ct")
    return pd.DataFrame({"critere": list(resultat.selected_orders),
                         "retards": [resultat.selected_orders[c] for c in resultat.selected_orders]})


def reponses(modele: Structurel, periodes: int = 50) -> np.ndarray:
    """Les réponses orthogonalisées : effet d'un choc d'un écart type sur chaque variable."""
    return modele.ajuste.irf(periodes).orth_irfs


def bandes(modele: Structurel, periodes: int = 50, repetitions: int = 200,
           couverture: float = 0.90, graine: int = 20211216) -> tuple[np.ndarray, np.ndarray]:
    """Un intervalle de confiance par rééchantillonnage, comme `irf(..., ci = 0.90)` en R."""
    np.random.seed(graine)
    basse, haute = modele.ajuste.irf(periodes).errband_mc(
        orth=True, repl=repetitions, signif=1 - couverture, seed=graine)
    return basse, haute


def decomposition(modele: Structurel, periodes: int = 10) -> pd.DataFrame:
    """La part de la variance de chaque variable expliquée par chaque choc, à l'horizon demandé."""
    parts = modele.ajuste.fevd(periodes).decomp[:, periodes - 1, :]
    return pd.DataFrame(parts, index=modele.variables, columns=modele.variables)


def table_reponses(modele: Structurel, choc: str, periodes: int = 50) -> pd.DataFrame:
    """Les réponses de toutes les variables à un choc donné, une ligne par mois."""
    j = modele.variables.index(choc)
    matrice = reponses(modele, periodes)[:, :, j]
    return pd.DataFrame(matrice, columns=modele.variables,
                        index=pd.RangeIndex(matrice.shape[0], name="periode"))
