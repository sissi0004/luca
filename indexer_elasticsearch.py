"""
Étape 4 du pipeline : INDEXATION.

Lit le résultat Parquet produit par le job Spark (prédictions par région)
depuis MinIO et l'indexe dans Elasticsearch (index `luca-predictions`),
avec un champ `region`, `latitude` et `longitude` pour permettre le filtrage
géographique côté application.

Usage :
    python scripts/indexer_elasticsearch.py
"""
import io

import boto3
import pandas as pd
from elasticsearch import Elasticsearch, helpers

from common_config import (
    ELASTICSEARCH_HOST,
    ELASTICSEARCH_INDEX,
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET_PROCESSED,
)

PREFIXE_PARQUET = "predictions_climat_region/"


def lire_parquet_depuis_minio() -> pd.DataFrame:
    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )
    objets = client.list_objects_v2(Bucket=MINIO_BUCKET_PROCESSED, Prefix=PREFIXE_PARQUET)
    fichiers_parquet = [
        o["Key"] for o in objets.get("Contents", []) if o["Key"].endswith(".parquet")
    ]

    trames = []
    for cle in fichiers_parquet:
        obj = client.get_object(Bucket=MINIO_BUCKET_PROCESSED, Key=cle)
        trames.append(pd.read_parquet(io.BytesIO(obj["Body"].read())))

    if not trames:
        return pd.DataFrame()
    return pd.concat(trames, ignore_index=True)


def indexer_dans_elasticsearch(df: pd.DataFrame):
    es = Elasticsearch([ELASTICSEARCH_HOST], request_timeout=30)
    if not es.ping():
        raise ConnectionError(f"Impossible de joindre Elasticsearch sur {ELASTICSEARCH_HOST}")

    actions = (
        {
            "_index": ELASTICSEARCH_INDEX,
            "_id": f"{row['pays']}_{row['region']}_{row['date_climat']}",
            "_source": row.to_dict(),
        }
        for _, row in df.iterrows()
    )
    succes, erreurs = helpers.bulk(es, actions, stats_only=False, raise_on_error=False)
    print(f"✅ {succes} documents indexés dans '{ELASTICSEARCH_INDEX}'.")
    if erreurs:
        print(f"⚠️ {len(erreurs)} erreurs lors de l'indexation (premier détail : {erreurs[0]})")


def executer():
    df = lire_parquet_depuis_minio()
    if df.empty:
        print("⚠️ Aucune donnée Parquet trouvée dans MinIO, indexation annulée.")
        return
    indexer_dans_elasticsearch(df)


if __name__ == "__main__":
    executer()
