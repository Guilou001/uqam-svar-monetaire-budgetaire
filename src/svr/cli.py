"""Ligne de commande : télécharger, estimer les deux blocs, dessiner."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="SVAR monétaire et budgétaire sur données américaines, identification récursive.")

# Le bloc budgétaire : trois ordres de récursivité, comme dans le code de 2021.
ORDRES_BUDGETAIRES = {"depense_dabord": ["G", "T", "Y"],
                      "impots_dabord": ["T", "G", "Y"],
                      "produit_dabord": ["Y", "G", "T"]}


@app.callback()
def main() -> None:
    """Sous-commandes nommées."""


@app.command()
def fetch() -> None:
    """Les seize séries de FRED, écrites dans `data/raw/` et jamais commitées."""
    from svr import donnees

    chemins = donnees.fetch()
    total = sum(c.stat().st_size for c in chemins.values())
    typer.echo(f"{len(chemins)} séries téléchargées, {total / 1e6:.2f} Mo au total")


@app.command()
def bases(out: Path = Path("results")) -> None:
    """Les deux tableaux, leur fenêtre et le nombre de cases manquantes, l'un et l'autre comptés."""
    import pandas as pd

    from svr import donnees

    d = donnees.charger()
    manquantes = donnees.bloc_mensuel().isna().sum()
    # le bloc trimestriel n'est pas comblé mais élagué : ce compte dit ce que le `dropna` a retiré
    manquantes_trimestrielles = int(donnees.bloc_trimestriel().isna().sum().sum())

    table = pd.DataFrame([
        {"bloc": "mensuel", "variables": d.mensuel.shape[1], "observations": len(d.mensuel),
         "premier": f"{d.mensuel.index[0]:%Y-%m}", "dernier": f"{d.mensuel.index[-1]:%Y-%m}",
         "cases_comblees": int(manquantes.sum())},
        {"bloc": "trimestriel", "variables": d.trimestriel.shape[1], "observations": len(d.trimestriel),
         "premier": f"{d.trimestriel.index[0]:%Y-%m}", "dernier": f"{d.trimestriel.index[-1]:%Y-%m}",
         "cases_comblees": manquantes_trimestrielles},
    ])
    (out / "tables").mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "tables" / "dimensions.csv", index=False)
    manquantes[manquantes > 0].to_csv(out / "tables" / "cases_comblees.csv", header=["mois"])
    typer.echo(table.to_string(index=False))
    typer.echo(f"\ncases comblées, par variable :\n{manquantes[manquantes > 0].to_string()}")


@app.command()
def lab(out: Path = Path("results"), repetitions: int = 200, periodes: int = 50) -> None:
    """Les quatre SVAR monétaires et les trois SVAR budgétaires, avec réponses et décompositions."""
    import warnings

    import pandas as pd

    warnings.filterwarnings("ignore")

    from svr import donnees, svar

    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    d = donnees.charger()

    resume = []
    for nom, (debut, fin, retards) in donnees.SOUS_ECHANTILLONS.items():
        bloc = d.mensuel.loc[debut:fin]
        modele = svar.estimer(bloc, retards, nom)
        table = svar.table_reponses(modele, "FFR", periodes)
        basse, haute = svar.bandes(modele, periodes, repetitions)
        j = modele.variables.index("FFR")
        table.to_csv(tables / f"reponses_monetaire_{nom}.csv")
        pd.DataFrame(basse[:, :, j], columns=modele.variables).to_csv(
            tables / f"reponses_monetaire_{nom}_basse.csv", index=False)
        pd.DataFrame(haute[:, :, j], columns=modele.variables).to_csv(
            tables / f"reponses_monetaire_{nom}_haute.csv", index=False)
        for horizon in (10, 12):
            svar.decomposition(modele, horizon).to_csv(
                tables / f"variance_monetaire_{nom}_h{horizon}.csv")
        creux = table["LIP"].idxmin()
        resume.append({"bloc": "monetaire", "echantillon": nom, "retards": retards,
                       "observations": modele.observations,
                       "hausse_immediate_ffr": round(float(table["FFR"].iloc[0]), 4),
                       "creux_production": int(creux),
                       "effet_creux_production_pct": round(100 * float(table["LIP"].min()), 4),
                       "effet_prix_12m_pct": round(100 * float(table["LCPI"].iloc[12]), 4)})
        typer.echo(f"monétaire {nom:11s} {modele.observations:4d} obs, choc {table['FFR'].iloc[0]:.3f} pt, "
                   f"creux de production {100 * table['LIP'].min():.2f} % au mois {creux}")

    for nom, ordre in ORDRES_BUDGETAIRES.items():
        bloc = d.trimestriel[ordre]
        modele = svar.estimer(bloc, 1, nom)
        for choc in ("G", "T"):
            svar.table_reponses(modele, choc, 20).to_csv(
                tables / f"reponses_budgetaire_{nom}_{choc}.csv")
        for horizon in (6, 10):
            svar.decomposition(modele, horizon).to_csv(
                tables / f"variance_budgetaire_{nom}_h{horizon}.csv")
        reponse = svar.table_reponses(modele, "G", 20)["Y"]
        reponse_impot = svar.table_reponses(modele, "T", 20)["Y"]
        resume.append({"bloc": "budgetaire", "echantillon": nom, "retards": 1,
                       "observations": modele.observations,
                       "effet_produit_immediat_pct": round(100 * float(reponse.iloc[0]), 4),
                       "effet_produit_max_pct": round(100 * float(reponse.max()), 4),
                       "trimestre_du_max": int(reponse.idxmax()),
                       "effet_impot_produit_20t_pct": round(100 * float(reponse_impot.iloc[-1]), 4),
                       "effet_depense_produit_20t_pct": round(100 * float(reponse.iloc[-1]), 4)})
        typer.echo(f"budgétaire {nom:15s} choc de dépense sur le produit : "
                   f"{100 * reponse.iloc[0]:.3f} % à l'impact, "
                   f"{100 * reponse.max():.3f} % au maximum (trimestre {reponse.idxmax()})")

    pd.DataFrame(resume).to_csv(tables / "resume.csv", index=False)


@app.command()
def retards(out: Path = Path("results")) -> None:
    """Les critères d'information sur le bloc monétaire complet, comme `VARselect` en R."""
    from svr import donnees, svar

    d = donnees.charger()
    table = svar.selection_retards(d.mensuel)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "tables" / "selection_retards.csv", index=False)
    typer.echo(table.to_string(index=False))


@app.command()
def figures(out: Path = Path("results")) -> None:
    """Les figures, reconstruites depuis les tables de `results/tables/`."""
    from svr import figures as fig

    for chemin in fig.toutes(out):
        typer.echo(f"écrit {chemin}")


if __name__ == "__main__":
    app()
