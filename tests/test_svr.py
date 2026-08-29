"""Les identités du travail vérifiées sans réseau : identification récursive, blocs, imputation."""

import numpy as np
import pandas as pd
import pytest

from svr.donnees import ORDRE_MENSUEL, SOUS_ECHANTILLONS, imputer
from svr.svar import decomposition, estimer, reponses, table_reponses


def _faux_bloc(n=400, k=4, graine=0):
    rng = np.random.default_rng(graine)
    a = np.eye(k) * 0.6 + rng.normal(0, 0.05, (k, k))
    bruit = rng.normal(0, 1, (n, k)) @ np.linalg.cholesky(np.eye(k) + 0.3 * np.ones((k, k))).T
    y = np.zeros((n, k))
    for t in range(1, n):
        y[t] = a @ y[t - 1] + bruit[t]
    index = pd.date_range("1965-01-01", periods=n, freq="MS")
    return pd.DataFrame(y, index=index, columns=[f"v{i}" for i in range(k)])


def test_la_matrice_a_est_l_inverse_du_facteur_de_cholesky():
    """L'identité que le portage repose : la matrice `Amat` triangulaire du code R de 2021 est
    l'inverse du facteur de Cholesky de la covariance des résidus, et son produit par ce facteur
    redonne l'identité."""
    modele = estimer(_faux_bloc(), retards=2)
    produit = modele.matrice_a @ modele.facteur
    assert np.allclose(produit, np.eye(len(modele.variables)), atol=1e-12)
    assert np.allclose(np.triu(modele.matrice_a, 1), 0.0, atol=1e-12)
    assert np.allclose(modele.facteur @ modele.facteur.T, np.asarray(modele.ajuste.sigma_u),
                       atol=1e-12)


def test_une_variable_ne_reagit_pas_dans_le_mois_a_un_choc_qui_la_suit():
    """La marque de l'identification récursive : à l'impact, la matrice des réponses est
    triangulaire inférieure. La première variable ne bouge donc pas le mois même d'un choc porté par
    la deuxième, alors que l'inverse est permis."""
    modele = estimer(_faux_bloc(), retards=2)
    impact = reponses(modele, periodes=4)[0]
    assert np.allclose(np.triu(impact, 1), 0.0, atol=1e-12)
    assert abs(impact[0, 1]) < 1e-12
    assert abs(impact[1, 0]) > 1e-9


def test_les_parts_de_variance_somment_a_un():
    modele = estimer(_faux_bloc(), retards=2)
    parts = decomposition(modele, periodes=10)
    assert np.allclose(parts.sum(axis=1).to_numpy(), 1.0, atol=1e-10)
    assert (parts.to_numpy() >= -1e-12).all()


def test_la_table_des_reponses_porte_le_bon_choc():
    modele = estimer(_faux_bloc(), retards=1)
    table = table_reponses(modele, "v1", periodes=6)
    assert list(table.columns) == modele.variables
    assert len(table) == 7
    # v0 précède v1 dans l'ordre : sa réponse au choc de v1 est nulle à l'impact
    assert table["v0"].iloc[0] == pytest.approx(0.0, abs=1e-12)


def test_l_imputation_ne_touche_qu_aux_cases_manquantes():
    """Les onze cases comblées du travail sont des logarithmes de réserves devenues négatives.
    L'imputation doit les remplir sans déplacer une seule valeur observée."""
    bloc = _faux_bloc(n=200, k=5, graine=3)
    troue = bloc.copy()
    troue.iloc[100:105, 2] = np.nan
    rempli = imputer(troue, composantes=2)
    assert not rempli.isna().any(axis=None)
    observees = troue.notna()
    assert np.allclose(rempli.where(observees).to_numpy()[observees.to_numpy()],
                       bloc.where(observees).to_numpy()[observees.to_numpy()], atol=1e-12)


def test_l_imputation_laisse_un_tableau_complet_inchange():
    bloc = _faux_bloc(n=120, k=3, graine=5)
    assert imputer(bloc).equals(bloc)


def test_les_sous_echantillons_sont_ceux_du_code_de_2021():
    """Le code R découpait en positions, `X[1:216]`, `X[217:516]` et `X[217:666]`. Sur un index
    mensuel qui commence en janvier 1965, ces bornes sont les dates retenues ici."""
    index = pd.date_range("1965-01-01", periods=666, freq="MS")
    assert f"{index[215]:%Y-%m}" == "1982-12"
    assert f"{index[216]:%Y-%m}" == "1983-01"
    assert f"{index[515]:%Y-%m}" == "2007-12"
    assert f"{index[665]:%Y-%m}" == "2020-06"
    assert SOUS_ECHANTILLONS["1965-1982"][:2] == ("1965-01-01", "1982-12-01")
    assert SOUS_ECHANTILLONS["1983-2007"][:2] == ("1983-01-01", "2007-12-01")


def test_l_ordre_des_variables_monetaires_est_celui_de_cee():
    """Quatre variables lentes, le taux directeur, puis trois variables financières."""
    assert ORDRE_MENSUEL == ["LIP", "UNEMP", "LPCOM", "LCPI", "FFR", "LM1", "LNBR", "LTR"]
    assert ORDRE_MENSUEL.index("FFR") == 4
