"""Les deux blocs de données du travail, rebâtis depuis FRED.

Le code R de 2021 lisait deux classeurs déposés à la main. Aucun des deux n'est public.

`Data.Q1.xlsx` portait les huit variables mensuelles de Christiano, Eichenbaum et Evans (1999),
décrites sur la page de Valerie Ramey. Elles se retrouvent une par une dans FRED, et c'est ce que ce
module télécharge. L'exception est le taux fantôme de Wu et Xia, que le travail employait comme
variante : l'adresse de la Fed d'Atlanta renvoie une page HTML et non le classeur, constat mesuré le
2026-08-29, donc cette variante est déclarée non reproduite plutôt que remplacée en silence.

`Data_General_Gvt.xlsx` venait de la base de Guay (2020), non publique. Le code de 2021 y additionnait
sept postes pour former la dépense publique, `wage + durable + nondurable + service + structure +
equip + intel`. Cette somme est, poste pour poste, la consommation publique augmentée de
l'investissement public, que FRED publie sous `GCE` : la substitution est donc une agrégation
équivalente, pas une approximation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RACINE = Path("data/raw")
ENTETE = {"User-Agent": "uqam-svar-monetaire-budgetaire (88989051+Guilou001@users.noreply.github.com)"}
BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# Les huit variables du bloc monétaire, dans l'ordre de récursivité de 2021.
MENSUELLES = {
    "INDPRO": ("LIP", "log"),          # production industrielle
    "UNRATE": ("UNEMP", "niveau"),     # taux de chômage
    "PPIACO": ("LPCOM", "log"),        # prix des matières premières
    "CPIAUCSL": ("LCPI", "log"),       # indice des prix à la consommation
    "FEDFUNDS": ("FFR", "niveau"),     # taux des fonds fédéraux
    "M1SL": ("LM1", "log"),            # masse monétaire M1
    "NONBORRES": ("LNBR", "log"),      # réserves non empruntées
    "TOTRESNS": ("LTR", "log"),        # réserves totales
}
ORDRE_MENSUEL = ["LIP", "UNEMP", "LPCOM", "LCPI", "FFR", "LM1", "LNBR", "LTR"]

# Le bloc budgétaire : la dépense, les recettes nettes et le produit intérieur brut.
TRIMESTRIELLES = {
    "GCE": "depense",                  # consommation et investissement publics
    "GRECPT": "recettes",              # recettes courantes des administrations
    "A084RC1Q027SBEA": "transferts",   # transferts courants versés
    "A180RC1Q027SBEA": "interets",     # intérêts versés
    "B096RC1Q027SBEA": "subventions",  # subventions
    "GDP": "pib",
    "GDPDEF": "deflateur",
    "B230RC0Q173SBEA": "population",   # milliers de personnes
}

DEBUT_MENSUEL, FIN_MENSUEL = "1965-01-01", "2020-06-01"
DEBUT_TRIMESTRIEL, FIN_TRIMESTRIEL = "1960-01-01", "2015-07-01"

# Les trois sous-échantillons du travail, en dates plutôt qu'en positions de ligne.
SOUS_ECHANTILLONS = {
    "complet": (DEBUT_MENSUEL, FIN_MENSUEL, 3),
    "1965-1982": ("1965-01-01", "1982-12-01", 2),
    "1983-2007": ("1983-01-01", "2007-12-01", 2),
    "1983-2020": ("1983-01-01", FIN_MENSUEL, 2),
}


@dataclass(frozen=True)
class Donnees:
    """Les deux tableaux prêts pour l'estimation, mensuel et trimestriel."""

    mensuel: pd.DataFrame
    trimestriel: pd.DataFrame


def _telecharger(identifiant: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    reponse = requests.get(BASE + identifiant, headers=ENTETE, timeout=120)
    reponse.raise_for_status()
    dest.write_bytes(reponse.content)
    return dest


def fetch(racine: Path = RACINE) -> dict[str, Path]:
    """Les seize séries de FRED, une par fichier, écrites dans `data/raw/`."""
    chemins = {}
    for identifiant in list(MENSUELLES) + list(TRIMESTRIELLES):
        chemins[identifiant] = _telecharger(identifiant, racine / f"{identifiant}.csv")
    return chemins


def _lire(identifiant: str, racine: Path) -> pd.Series:
    brut = pd.read_csv(racine / f"{identifiant}.csv")
    brut[brut.columns[0]] = pd.to_datetime(brut[brut.columns[0]])
    serie = brut.set_index(brut.columns[0]).iloc[:, 0]
    serie.index.name = "date"
    serie.name = identifiant
    return pd.to_numeric(serie, errors="coerce")


def imputer(tableau: pd.DataFrame, composantes: int = 2) -> pd.DataFrame:
    """Comble les valeurs manquantes par une analyse en composantes principales itérative.

    Le code R de 2021 appelait `imputePCA(ncp = 2)`. La méthode est la même ici : les colonnes sont
    centrées et réduites, deux composantes sont estimées, et les cases manquantes sont remplacées par
    leur projection, l'opération étant répétée jusqu'à convergence.

    Ce n'est pas un détail de confort. Les réserves non empruntées sont devenues négatives de la fin
    de 2008 à 2010, et leur logarithme n'existe pas sur ces mois-là : ce sont ces cases que le travail
    de 2021 comblait.
    """
    from statsmodels.multivariate.pca import PCA

    if not tableau.isna().any(axis=None):
        return tableau
    ajuste = PCA(tableau, ncomp=composantes, missing="fill-em", standardize=True)
    complet = pd.DataFrame(ajuste._adjusted_data, index=tableau.index, columns=tableau.columns)
    return tableau.where(tableau.notna(), complet)


def charger(racine: Path = RACINE) -> Donnees:
    """Les deux tableaux, sur les fenêtres du travail de 2021."""
    colonnes = {}
    for identifiant, (nom, forme) in MENSUELLES.items():
        serie = _lire(identifiant, racine).loc[DEBUT_MENSUEL:FIN_MENSUEL]
        colonnes[nom] = np.log(serie.where(serie > 0)) if forme == "log" else serie
    mensuel = imputer(pd.DataFrame(colonnes)[ORDRE_MENSUEL])

    brut = {nom: _lire(identifiant, racine).loc[DEBUT_TRIMESTRIEL:FIN_TRIMESTRIEL]
            for identifiant, nom in TRIMESTRIELLES.items()}
    table = pd.DataFrame(brut)
    depense_nette = table["recettes"] - table["transferts"] - table["interets"] - table["subventions"]
    par_tete = 1e9 * 100.0 / (table["population"] * 1000.0)
    trimestriel = pd.DataFrame({
        "G": np.log(table["depense"] / table["deflateur"] * par_tete),
        "T": np.log(depense_nette / table["deflateur"] * par_tete),
        "Y": np.log(table["pib"] * 1e9 / (table["population"] * 1000.0)),
    }).dropna()

    return Donnees(mensuel, trimestriel)
