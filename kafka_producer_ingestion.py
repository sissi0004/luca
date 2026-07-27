"""
Étape 1 du pipeline : INGESTION.

Interroge l'API météo publique Open-Meteo (gratuite, sans clé) pour chaque
région définie dans `regions_config.py`, et publie chaque mesure comme
message JSON sur le topic Kafka `weather-raw-regions`.

⚠️ Important : on récupère un historique quotidien réel de plusieurs jours
(`past_days`) en un seul appel, pas juste l'instant présent. Le job Spark
calcule des features J-1/J-2 (température de la veille et de l'avant-veille)
pour entraîner sa régression linéaire — avec une seule mesure par région,
ce fenêtrage ne peut produire aucune ligne exploitable et l'entraînement
plante avec "Training dataset is empty". Ce backfill résout le problème dès
le premier run, sans avoir à relancer le pipeline plusieurs jours de suite.

Usage :
    python scripts/kafka_producer_ingestion.py
"""
import json
import time
from datetime import datetime

import requests
from kafka import KafkaProducer

from common_config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_WEATHER, OPEN_METEO_URL
from regions_config import toutes_les_regions_a_plat

NB_JOURS_HISTORIQUE = 5  # jours passés récupérés en plus d'aujourd'hui (>= 2 requis pour J-1/J-2)


def creer_producteur():
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )


def recuperer_historique_region(lat: float, lon: float) -> list[dict]:
    """Appelle Open-Meteo pour une position donnée et retourne un historique quotidien réel
    (moyenne du jour) sur NB_JOURS_HISTORIQUE jours passés + aujourd'hui."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,precipitation_sum",
        "past_days": NB_JOURS_HISTORIQUE,
        "forecast_days": 1,
        "timezone": "auto",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=15)
    resp.raise_for_status()
    quotidien = resp.json().get("daily", {})

    dates = quotidien.get("time", [])
    temperatures = quotidien.get("temperature_2m_mean", [])
    humidites = quotidien.get("relative_humidity_2m_mean", [])
    precipitations = quotidien.get("precipitation_sum", [])

    historique = []
    for i, date_str in enumerate(dates):
        horodatage = int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())
        historique.append({
            "date_climat": horodatage,
            "temperature": temperatures[i] if i < len(temperatures) else None,
            "humidite": humidites[i] if i < len(humidites) else None,
            "precipitations": precipitations[i] if i < len(precipitations) else 0.0,
        })
    return historique


def ingerer_toutes_les_regions():
    producteur = creer_producteur()
    regions = toutes_les_regions_a_plat()
    print(f"📥 Ingestion météo (historique {NB_JOURS_HISTORIQUE}j + aujourd'hui) pour {len(regions)} régions...")

    nb_messages, nb_erreur = 0, 0
    for pays, region, lat, lon, iso3 in regions:
        try:
            historique = recuperer_historique_region(lat, lon)
            for jour in historique:
                message = {
                    "pays": pays,
                    "region": region,
                    "iso3": iso3,
                    "latitude": lat,
                    "longitude": lon,
                    **jour,
                }
                producteur.send(KAFKA_TOPIC_WEATHER, value=message)
                nb_messages += 1
        except Exception as e:
            nb_erreur += 1
            print(f"⚠️ Échec ingestion pour {pays} / {region} : {e}")

    producteur.flush()
    producteur.close()
    print(f"✅ Ingestion terminée : {nb_messages} mesures envoyées sur Kafka "
          f"({len(regions)} régions × ~{NB_JOURS_HISTORIQUE + 1} jours), {nb_erreur} erreurs.")


if __name__ == "__main__":
    ingerer_toutes_les_regions()
