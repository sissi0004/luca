# 🌍 LUCA — Logical Unified Climate Analytics

**Application web d'analyse comparative des données météorologiques et de l'impact du réchauffement climatique entre plusieurs pays.**

LUCA est une plateforme web d'intelligence climatique conçue pour collecter, centraliser et analyser des données météorologiques provenant de plusieurs pays et de leurs régions. Elle permet de comparer les tendances climatiques, de détecter les anomalies météorologiques et d'évaluer l'impact du réchauffement climatique grâce à des visualisations interactives et des analyses basées sur les données.

---

## 🏗️ Architecture technique (Big Data)

```
Open-Meteo (API météo, par région)
        │
        ▼
   Kafka Producer  ──▶  Kafka (topic weather-raw-regions)
        │                        │
        │                        ▼
        │                 Kafka Consumer ──▶ MinIO (bucket weather-raw, JSON brut)
        │                                            │
        │                                            ▼
        │                                   Spark / SparkML (fenêtres J-1/J-2,
        │                                   régression linéaire par région)
        │                                            │
        │                                            ▼
        │                                   MinIO (bucket weather-processed, Parquet)
        │                                            │
        │                                            ▼
        │                                   Elasticsearch (index luca-predictions)
        │                                            │
        └────────────── orchestré par Airflow ───────┘
                                                       ▼
                                     Application Flask (3 pages)
```

* **Ingestion :** appel de l'API météo publique **Open-Meteo** (gratuite, sans clé) pour chaque région définie dans `scripts/regions_config.py`, publication sur **Kafka**. Chaque appel récupère **5 jours d'historique réel + aujourd'hui** (paramètre `past_days`) plutôt qu'un simple instantané : le job Spark a besoin d'au moins 2 jours d'historique par région (J-1, J-2) pour entraîner sa régression, ce backfill évite l'erreur `Training dataset is empty` au premier run.
* **Data Lake :** **MinIO** (S3-compatible) archive les mesures brutes en JSON, puis les résultats en **Parquet (Snappy)**.
* **Traitement & ML :** **Apache Spark (PySpark & SparkML)** calcule les fenêtres temporelles J-1/J-2 par région et entraîne une régression linéaire pour prédire la température du lendemain.
* **Indexation :** **Elasticsearch** stocke les documents unifiés (pays, région, coordonnées, température, prédiction, humidité, précipitations).
* **Orchestration :** **Apache Airflow** exécute quotidiennement le pipeline complet via le DAG `pipeline_predictions_climatiques`.
* **Interface utilisateur :** une **application Flask unique** (Jinja2 + Bootstrap + Plotly), à 3 pages :
  1. 🗺️ **Carte Mondiale** (`/`) — choroplèthe par pays + zoom interactif sur les régions.
  2. 🔍 **Analyse & Prédictions** (`/analyse`) — anomalies, recommandations, prédiction J+1, par pays ou par région.
  3. 📊 **Dashboard** (`/dashboard`) — indicateurs clés, tendances, export CSV.

> ⚠️ **Sécurité :** une clé API tierce était présente en clair dans `notebook/work/exploration_api.ipynb`. Elle a été retirée du pipeline (remplacée par Open-Meteo, sans clé) mais **doit être révoquée** si elle est encore active, et ne doit plus être commit.

---

## 🚀 Installation et lancement — 100% Docker

### 1. Prérequis
* Docker et Docker Compose
* **Machines à 8 Go de RAM ou moins :** ouvrir Docker Desktop → Settings ⚙️ → Resources et régler **Memory à 5 Go maximum** (laisse 3 Go à l'OS). Chaque service a une limite mémoire définie dans `docker-compose.yml` (`mem_limit`) calibrée pour tenir dans cette enveloppe (total ≈ 5 Go : web 300M, minio 400M, kafka 900M, elasticsearch 1200M, spark-jupyter 1500M, airflow 700M). Si tu as plus de RAM disponible, tu peux augmenter ces valeurs pour de meilleures performances.
* Si le notebook Spark plante avec une erreur de connexion serveur, vérifie d'abord `docker compose logs spark-jupyter --tail 100` à la recherche de `Killed` / `OOMKilled` / code `137` (= manque de mémoire).

### 2. Lancement complet
```bash
docker compose up -d --build
```

Cela démarre l'ensemble des services sur le réseau `luca-network` :

| Service        | Port(s)       | Rôle                                   |
|----------------|---------------|-----------------------------------------|
| `web`          | 5000          | Application Flask LUCA                  |
| `minio`        | 9000 / 9001   | Data lake S3-compatible                 |
| `kafka`        | 9092          | Ingestion en flux                       |
| `elasticsearch`| 9200          | Moteur d'indexation / requêtes          |
| `spark-jupyter`| 8888 / 4040   | Traitement Spark & notebooks            |
| `airflow`      | 8080          | Orchestration du pipeline (`@daily`)    |

### 3. Accéder à l'application
[http://localhost:5000](http://localhost:5000)

> 💡 Tant que le pipeline n'a pas encore tourné (index Elasticsearch vide), l'application affiche automatiquement un jeu de données de démonstration généré à partir du référentiel de régions, pour rester utilisable dès le premier lancement.

### 4. Activer le pipeline
Ouvrir [http://localhost:8080](http://localhost:8080) et activer le DAG `pipeline_predictions_climatiques` (planifié `@daily`), ou le déclencher manuellement depuis l'interface Airflow.

### 5. Lancer le pipeline manuellement (optionnel, pour tester sans attendre Airflow)
```bash
docker compose exec airflow python /opt/scripts/kafka_producer_ingestion.py
docker compose exec airflow python /opt/scripts/kafka_consumer_to_minio.py
docker compose exec spark-jupyter spark-submit \
  --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
  /opt/spark-apps/traitement_climat_region.py
docker compose exec airflow python /opt/scripts/indexer_elasticsearch.py
```

---

## 📁 Structure du projet

```
Climat_project/
├── app.py                            # Application Flask (routes des 3 pages)
├── services.py                       # Connexion ES, données démo, Humidex, anomalies (partagé)
├── templates/
│   ├── base.html                     # Layout commun (navigation)
│   ├── carte.html                    # Page 1 : carte mondiale
│   ├── analyse.html                  # Page 2 : analyse & prédictions
│   └── dashboard.html                # Page 3 : dashboard
├── Dockerfile                        # Image de l'application Flask
├── scripts/
│   ├── regions_config.py             # Référentiel pays/régions (coordonnées)
│   ├── common_config.py              # Config centralisée (hôtes ES/MinIO/Kafka)
│   ├── kafka_producer_ingestion.py   # Ingestion Open-Meteo -> Kafka
│   ├── kafka_consumer_to_minio.py    # Kafka -> MinIO (JSON brut)
│   └── indexer_elasticsearch.py      # MinIO (Parquet) -> Elasticsearch
├── spark/apps/
│   └── traitement_climat_region.py   # Job Spark ML (fenêtres J-1/J-2, régression linéaire)
├── airflow/dags/
│   └── dag_climat.py                 # Orchestration du pipeline complet
├── docker-compose.yml
└── requirements.txt
```
