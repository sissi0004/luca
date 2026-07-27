"""
Référentiel central des pays et régions couverts par LUCA.
Chaque région est définie par ses coordonnées (latitude, longitude), utilisées
pour l'ingestion météo (Open-Meteo) et pour l'affichage cartographique.

⚠️ Fichier partagé par : les scripts d'ingestion, le job Spark, l'indexation
Elasticsearch et l'application Streamlit. Ne pas dupliquer cette liste ailleurs.
"""

# Code ISO3 (pour la carte choroplèthe monde) + régions représentatives (grandes villes / capitales régionales)
PAYS_REGIONS = {
    "Senegal": {
        "iso3": "SEN",
        "centre": (14.4974, -14.4524),
        "regions": {
            "Dakar": (14.6928, -17.4467),
            "Thies": (14.7910, -16.9256),
            "Saint-Louis": (16.0179, -16.4896),
            "Ziguinchor": (12.5665, -16.2733),
            "Kaolack": (14.1652, -16.0726),
            "Tambacounda": (13.7707, -13.6673),
        },
    },
    "Mali": {
        "iso3": "MLI",
        "centre": (17.5707, -3.9962),
        "regions": {
            "Bamako": (12.6392, -8.0029),
            "Sikasso": (11.3167, -5.6667),
            "Segou": (13.4317, -6.2157),
            "Mopti": (14.4843, -4.1826),
            "Gao": (16.2666, -0.0500),
            "Kayes": (14.4469, -11.4456),
        },
    },
    "Benin": {
        "iso3": "BEN",
        "centre": (9.3077, 2.3158),
        "regions": {
            "Cotonou": (6.3703, 2.3912),
            "Porto-Novo": (6.4969, 2.6289),
            "Parakou": (9.3372, 2.6303),
            "Abomey": (7.1826, 1.9924),
            "Natitingou": (10.3042, 1.3792),
        },
    },
    "Comores": {
        "iso3": "COM",
        "centre": (-11.6455, 43.3333),
        "regions": {
            "Moroni (Ngazidja)": (-11.7022, 43.2551),
            "Mutsamudu (Anjouan)": (-12.1667, 44.4000),
            "Fomboni (Moheli)": (-12.3000, 43.7333),
        },
    },
    "France": {
        "iso3": "FRA",
        "centre": (46.2276, 2.2137),
        "regions": {
            "Paris (Ile-de-France)": (48.8566, 2.3522),
            "Marseille (PACA)": (43.2965, 5.3698),
            "Lyon (Auvergne-Rhone-Alpes)": (45.7640, 4.8357),
            "Toulouse (Occitanie)": (43.6047, 1.4442),
            "Lille (Hauts-de-France)": (50.6292, 3.0573),
            "Strasbourg (Grand Est)": (48.5734, 7.7521),
        },
    },
    "USA": {
        "iso3": "USA",
        "centre": (37.0902, -95.7129),
        "regions": {
            "New York": (40.7128, -74.0060),
            "Los Angeles": (34.0522, -118.2437),
            "Chicago": (41.8781, -87.6298),
            "Houston": (29.7604, -95.3698),
            "Miami": (25.7617, -80.1918),
            "Seattle": (47.6062, -122.3321),
        },
    },
}


def liste_pays():
    return sorted(PAYS_REGIONS.keys())


def liste_regions(pays: str):
    return sorted(PAYS_REGIONS.get(pays, {}).get("regions", {}).keys())


def coordonnees_region(pays: str, region: str):
    return PAYS_REGIONS.get(pays, {}).get("regions", {}).get(region)


def iso3(pays: str):
    return PAYS_REGIONS.get(pays, {}).get("iso3")


def toutes_les_regions_a_plat():
    """Retourne une liste de tuples (pays, region, lat, lon, iso3) pour tout le référentiel."""
    out = []
    for pays, infos in PAYS_REGIONS.items():
        for region, (lat, lon) in infos["regions"].items():
            out.append((pays, region, lat, lon, infos["iso3"]))
    return out
