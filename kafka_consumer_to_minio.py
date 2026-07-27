"""
Étape 2 du pipeline : ARCHIVAGE DANS LE DATA LAKE.

Consomme les messages météo par région publiés sur Kafka et les écrit dans le
bucket MinIO `weather-raw`, un fichier JSON par mesure, au format :
    brut_<Pays>_<Region>_<timestamp>.json

Ce consumer tourne en mode "batch" : il lit tout ce qui est disponible sur le
topic puis s'arrête (adapté à une exécution planifiée par Airflow). Pour un
mode continu, retirer `consumer_timeout_ms`.

Usage :
    python scripts/kafka_consumer_to_minio.py
"""

import re
import json

import boto3
from kafka import KafkaConsumer

from common_config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_WEATHER,
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW,
)


def creer_client_minio():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def s3_assurer_bucket(client, bucket: str):
    buckets_existants = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket not in buckets_existants:
        client.create_bucket(Bucket=bucket)


def consommer_et_archiver():
    client_minio = creer_client_minio()
    s3_assurer_bucket(client_minio, MINIO_BUCKET_RAW)

    consumer = KafkaConsumer(
        KAFKA_TOPIC_WEATHER,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        consumer_timeout_ms=10000,  # s'arrête après 10s d'inactivité (mode batch)
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    nb_ecrits = 0
    for message in consumer:
        record = message.value
        pays = record.get("pays", "inconnu")
        region = re.sub(r"[^A-Za-z0-9_-]", "-", record.get("region", "inconnue"))
        horodatage = record.get("date_climat")
        key = f"brut_{pays}_{region}_{horodatage}.json"

        client_minio.put_object(
            Bucket=MINIO_BUCKET_RAW,
            Key=key,
            Body=json.dumps(record, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        nb_ecrits += 1

    consumer.close()
    print(f" {nb_ecrits} mesures régionales archivées dans MinIO (bucket '{MINIO_BUCKET_RAW}').")


if __name__ == "__main__":
    consommer_et_archiver()
