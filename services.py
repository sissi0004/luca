"""
Couche de services de l'application LUCA — indépendante du framework web.
Centralise la connexion Elasticsearch, le chargement des données (avec repli
sur un jeu de démonstration si le pipeline n'a pas encore tourné) et la
logique d'analyse climatique (Humidex, détection d'anomalies).
"""
import math
import sys
import os
import time
import random

import pandas as pd
from elasticsearch import Elasticsearch

sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))
from common_config import ELASTICSEARCH_HOST, ELASTICSEARCH_INDEX  # noqa: E402
from regions_config import (  # noqa: E402
    PAYS_REGIONS, liste_pays, liste_regions, coordonnees_region,
    toutes_les_regions_a_plat,
)

COULEURS = {
    "primaire": "#1E3A8A",
    "danger": "#EF4444",
    "warning": "#F59E0B",
    "succes": "#10B981",
    "info": "#3B82F6",
}

_ES_CLIENT = None
_CACHE_DONNEES = {}
_CACHE_TTL_SECONDES = 300


def connecter_elasticsearch():
    """Connexion Elasticsearch mise en cache au niveau du process (pas de reconnexion à chaque requête)."""
    global _ES_CLIENT
    if _ES_CLIENT is not None:
        return _ES_CLIENT
    try:
        es = Elasticsearch([ELASTICSEARCH_HOST], request_timeout=10)
        if es.ping():
            _ES_CLIENT = es
            return es
    except Exception as e:
        print(f"❌ Erreur de connexion à Elasticsearch : {e}")
    return None


def charger_donnees(pays: str = None, region: str = None) -> pd.DataFrame:
    """Charge l'historique + prédictions depuis Elasticsearch, filtré par pays et/ou région.
    Repli automatique sur un jeu de données de démonstration si Elasticsearch est
    vide ou indisponible, pour que l'app reste utilisable avant le premier run du pipeline.
    Résultat mis en cache 5 minutes pour éviter de marteler Elasticsearch à chaque clic."""
    cle_cache = (pays, region)
    maintenant = time.time()
    if cle_cache in _CACHE_DONNEES:
        horodatage, df_cache = _CACHE_DONNEES[cle_cache]
        if maintenant - horodatage < _CACHE_TTL_SECONDES:
            return df_cache.copy()

    df = _charger_depuis_elasticsearch(pays, region)
    if df.empty:
        df = _donnees_demo(pays, region)

    _CACHE_DONNEES[cle_cache] = (maintenant, df)
    return df.copy()


def _charger_depuis_elasticsearch(pays: str = None, region: str = None) -> pd.DataFrame:
    es = connecter_elasticsearch()
    if not es:
        return pd.DataFrame()

    filtres = []
    if pays:
        filtres.append({"term": {"pays.keyword": pays}})
    if region:
        filtres.append({"term": {"region.keyword": region}})

    query = {
        "size": 2000,
        "query": {"bool": {"filter": filtres}} if filtres else {"match_all": {}},
        "sort": [{"date_climat": {"order": "asc"}}],
    }
    try:
        response = es.search(index=ELASTICSEARCH_INDEX, body=query)
        hits = response["hits"]["hits"]
        if hits:
            return pd.DataFrame([h["_source"] for h in hits])
    except Exception as e:
        print(f"⚠️ Requête Elasticsearch échouée : {e}")
    return pd.DataFrame()


def _donnees_demo(pays: str = None, region: str = None) -> pd.DataFrame:
    """Génère un jeu de données de démonstration réaliste à partir du référentiel de régions.
    Chaque région a sa propre graine aléatoire (dérivée de son nom) : ça garantit des valeurs
    différentes et cohérentes d'une région à l'autre, plutôt qu'une graine globale réinitialisée
    à chaque appel qui produisait exactement la même série pour deux régions demandées séparément."""
    lignes = []
    for p, r, lat, lon, iso3 in toutes_les_regions_a_plat():
        if pays and p != pays:
            continue
        if region and r != region:
            continue
        rng = random.Random(f"{p}_{r}")  # graine déterministe MAIS propre à cette région
        base_temp = 28 if p in ("Senegal", "Mali", "Benin", "Comores") else 16
        for j in range(10):
            temp = base_temp + rng.uniform(-4, 4)
            lignes.append({
                "pays": p, "region": r, "iso3": iso3,
                "latitude": lat, "longitude": lon,
                "date_climat": int(time.time()) - (10 - j) * 86400,
                "temperature": round(temp, 1),
                "temperature_predite": round(temp + rng.uniform(-1.5, 1.5), 1),
                "humidite": round(rng.uniform(30, 90), 1),
                "precipitations": round(max(0, rng.uniform(-5, 15)), 1),
            })
    return pd.DataFrame(lignes)


def calculer_humidex(temp_c: float, humidite_pct: float) -> float:
    """Indice Humidex simplifié (stress thermique perçu)."""
    try:
        e = 6.11 * math.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + temp_c))))
        return round(temp_c + (5 / 9) * (e * (humidite_pct / 100) - 10), 1)
    except (ValueError, ZeroDivisionError):
        return temp_c


def analyser_anomalies(temp_actuelle: float, humidite: float, precipitations: float):
    """Retourne une liste de (type, titre, texte). type ∈ {danger, warning, succes}.
    S'il n'y a aucune anomalie, retourne un message positif plutôt qu'une liste vide."""
    messages = []

    if temp_actuelle > 35.0:
        messages.append(("danger", "🔥 Anomalie thermique positive",
                          f"Vague de chaleur extrême détectée ({temp_actuelle:.1f}°C). "
                          "Recommandation : limiter les activités extérieures aux heures fraîches, "
                          "renforcer l'hydratation et surveiller les cultures sensibles à la chaleur."))
    elif temp_actuelle < 12.0:
        messages.append(("danger", "❄️ Anomalie thermique négative",
                          f"Vague de froid anormale ({temp_actuelle:.1f}°C). "
                          "Recommandation : protéger les cultures sensibles au gel et prévoir un chauffage d'appoint."))

    if humidite < 30.0 and temp_actuelle > 30.0:
        messages.append(("warning", "🏜️ Risque d'aridité élevé",
                          "Air très sec couplé à de fortes chaleurs : risque d'évapotranspiration des sols. "
                          "Recommandation : renforcer l'irrigation et pailler les sols exposés."))

    if precipitations < 2.0:
        messages.append(("warning", "📉 Déficit de précipitations",
                          "Cumul de pluie très faible sur la période. "
                          "Recommandation : anticiper l'irrigation et surveiller les réserves en eau."))
    elif precipitations > 50.0:
        messages.append(("warning", "🌧️ Excès de précipitations",
                          "Cumul de pluie important sur la période. "
                          "Recommandation : vérifier le drainage des parcelles pour éviter l'engorgement des sols."))

    if not messages:
        messages.append(("succes", "✅ Climat stable",
                          "Aucune anomalie détectée : température, humidité et précipitations sont "
                          "conformes aux équilibres saisonniers habituels de la région. Rien à signaler."))

    return messages


def carte_couleur_type(type_msg: str) -> str:
    return {"danger": COULEURS["danger"], "warning": COULEURS["warning"], "succes": COULEURS["succes"]}.get(
        type_msg, COULEURS["info"]
    )
