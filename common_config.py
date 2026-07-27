"""
Configuration centralisée. Toutes les valeurs sont surchargeables via variables
d'environnement, ce qui permet au même code de tourner :
- en local (hors Docker) -> localhost
- dans un conteneur du réseau luca-network -> noms de services Docker
"""
import os

ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "http://localhost:9200")
ELASTICSEARCH_INDEX = os.environ.get("ELASTICSEARCH_INDEX", "luca-predictions")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "luca_admin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "luca_password")
MINIO_BUCKET_RAW = os.environ.get("MINIO_BUCKET_RAW", "weather-raw")
MINIO_BUCKET_PROCESSED = os.environ.get("MINIO_BUCKET_PROCESSED", "weather-processed")

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_WEATHER = os.environ.get("KAFKA_TOPIC_WEATHER", "weather-raw-regions")

# API météo publique et gratuite (pas de clé requise) utilisée pour l'ingestion par région
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
