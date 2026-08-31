"""Les figures, redessinées depuis les tables de `results/tables/`."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]

LIBELLES = {
    "LIP": "Production industrielle (%)", "UNEMP": "Taux de chômage (points)",
    "LPCOM": "Prix des matières premières (%)", "LCPI": "Prix à la consommation (%)",
    "FFR": "Taux des fonds fédéraux (points)", "LM1": "Monnaie M1 (%)",
    "LNBR": "Réserves non empruntées (%)", "LTR": "Réserves totales (%)",
    "G": "Dépense publique (%)", "T": "Recettes nettes (%)", "Y": "Produit intérieur brut (%)",
}
ECHELLE_POURCENT = {"LIP", "LPCOM", "LCPI", "LM1", "LNBR", "LTR", "G", "T", "Y"}


def use_style():
    import matplotlib as mpl
    from cycler import cycler
    from matplotlib.ticker import FuncFormatter

    mpl.rcParams.update({
        "figure.dpi": 200, "savefig.dpi": 200, "figure.constrained_layout.use": True,
        "font.size": 10, "axes.titlesize": 11, "axes.prop_cycle": cycler(color=OKABE_ITO),
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
        "legend.frameon": False, "lines.linewidth": 1.4,
    })
    return FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))


def _fr(x: float, n: int = 2) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def _mise_a_l_echelle(colonne: str, valeurs: np.ndarray) -> np.ndarray:
    return 100 * valeurs if colonne in ECHELLE_POURCENT else valeurs


def fig_reponses(table: pd.DataFrame, basse: pd.DataFrame, haute: pd.DataFrame, titre: str,
                 dest: Path) -> Path:
    """Les réponses de toutes les variables à un choc, avec leur intervalle."""
    fr = use_style()
    colonnes = list(table.columns)
    lignes = int(np.ceil(len(colonnes) / 4))
    fig, axes = plt.subplots(lignes, 4, figsize=(13.0, 3.0 * lignes))
    plats = np.atleast_1d(axes).ravel()
    for ax in plats[len(colonnes):]:
        ax.set_visible(False)

    periodes = np.arange(len(table))
    for ax, colonne in zip(plats, colonnes, strict=False):
        centre = _mise_a_l_echelle(colonne, table[colonne].to_numpy())
        ax.fill_between(periodes, _mise_a_l_echelle(colonne, basse[colonne].to_numpy()),
                        _mise_a_l_echelle(colonne, haute[colonne].to_numpy()),
                        color=OKABE_ITO[5], alpha=0.25)
        ax.plot(periodes, centre, color=OKABE_ITO[0])
        ax.axhline(0.0, color="black", lw=0.8)
        ax.set_title(LIBELLES.get(colonne, colonne), fontsize=9.5)
        ax.tick_params(labelsize=8)
        ax.yaxis.set_major_formatter(fr)
    fig.supxlabel("Mois écoulés depuis le choc", fontsize=9.5)
    fig.suptitle(titre, fontsize=11)
    fig.savefig(dest)
    plt.close(fig)
    return dest


def fig_budgetaire(reponses: dict[str, pd.DataFrame], dest: Path) -> Path:
    """L'effet d'un choc de dépense sur le produit, selon l'ordre de récursivité retenu."""
    fr = use_style()
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    for k, (nom, table) in enumerate(sorted(reponses.items())):
        serie = 100 * table["Y"].to_numpy()
        ax.plot(np.arange(len(serie)), serie, color=OKABE_ITO[k % len(OKABE_ITO)],
                marker="o", ms=3, label=nom.replace("_", " "))
    ax.axhline(0.0, color="black", lw=0.8)
    # les trimestres se comptent un par un : l'axe ne doit pas afficher de demi-trimestre
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Trimestres écoulés depuis le choc")
    ax.set_ylabel("Réponse du produit intérieur brut nominal\npar habitant (%)", fontsize=9.5)
    ax.yaxis.set_major_formatter(fr)
    ax.legend(fontsize=9)
    ecarts = {nom: 100 * float(t["Y"].max()) for nom, t in reponses.items()}
    etendue = max(ecarts.values()) - min(ecarts.values())
    ax.set_title("Réponse du produit à un choc de dépense publique : les trois ordres de récursivité "
                 f"s'écartent de {_fr(etendue)} point au maximum", fontsize=10.5)
    fig.savefig(dest)
    plt.close(fig)
    return dest


def fig_variance(decomposition: pd.DataFrame, titre: str, dest: Path) -> Path:
    """La part de la variance de chaque variable expliquée par chaque choc."""
    use_style()
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    bas = np.zeros(len(decomposition))
    positions = np.arange(len(decomposition))
    for k, choc in enumerate(decomposition.columns):
        parts = 100 * decomposition[choc].to_numpy()
        ax.bar(positions, parts, bottom=bas, color=OKABE_ITO[k % len(OKABE_ITO)],
               label=LIBELLES.get(choc, choc).split(" (")[0])
        bas += parts
    ax.set_xticks(positions)
    ax.set_xticklabels([LIBELLES.get(v, v).split(" (")[0] for v in decomposition.index],
                       rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Part de la variance expliquée (%)")
    ax.legend(fontsize=8, ncols=4)
    ax.set_title(titre, fontsize=10.5)
    fig.savefig(dest)
    plt.close(fig)
    return dest


def titre_monetaire(nom: str, table: pd.DataFrame) -> str:
    """Le titre d'une figure de réponses, déduit de la table que cette figure dessine.

    Le creux ne s'annonce que s'il existe. Sur 1983-2007 la production ne repasse jamais sous son
    niveau de départ, et le minimum de la colonne y vaut exactement zéro, au mois zéro : écrire
    « creux à 0,00 % au mois 0 » dirait alors le contraire de ce que la courbe montre.
    """
    bas = 100 * float(table["LIP"].min())
    if bas >= 0:
        fin = "la production ne descend jamais sous son niveau de départ"
    else:
        fin = f"la production touche son creux à {_fr(bas)} % au mois {int(table['LIP'].idxmin())}"
    return (f"Choc de politique monétaire, échantillon {nom.replace('complet', '1965-2020')} : "
            f"{fin}\n"
            "La bande est l'intervalle à 90 % par tirages de Monte-Carlo")


def toutes(out: Path = Path("results")) -> list[Path]:
    """Toutes les figures que les tables présentes permettent de dessiner."""
    from svr.donnees import SOUS_ECHANTILLONS

    tables, figs = out / "tables", out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    ecrites = []

    for nom in SOUS_ECHANTILLONS:
        chemin = tables / f"reponses_monetaire_{nom}.csv"
        if not chemin.exists():
            continue
        table = pd.read_csv(chemin, index_col=0)
        basse = pd.read_csv(tables / f"reponses_monetaire_{nom}_basse.csv")
        haute = pd.read_csv(tables / f"reponses_monetaire_{nom}_haute.csv")
        ecrites.append(fig_reponses(table, basse, haute, titre_monetaire(nom, table),
                                    figs / f"reponses_monetaire_{nom}.png"))

    chemin = tables / "variance_monetaire_complet_h10.csv"
    if chemin.exists():
        decomposition = pd.read_csv(chemin, index_col=0)
        part = 100 * float(decomposition.loc["LIP", "FFR"])
        ecrites.append(fig_variance(
            decomposition,
            "Décomposition de la variance à dix mois, échantillon 1965-2020 : le choc de taux "
            f"explique {_fr(part)} % de la variance de la production", figs / "variance_monetaire.png"))

    reponses = {}
    for nom in ("depense_dabord", "impots_dabord", "produit_dabord"):
        chemin = tables / f"reponses_budgetaire_{nom}_G.csv"
        if chemin.exists():
            reponses[nom] = pd.read_csv(chemin, index_col=0)
    if reponses:
        ecrites.append(fig_budgetaire(reponses, figs / "reponses_budgetaire.png"))
    return ecrites
