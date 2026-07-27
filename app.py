"""
LUCA — Application Flask unifiée.

Application web d'analyse comparative des données météorologiques et de
l'impact du réchauffement climatique entre plusieurs pays. LUCA collecte,
centralise et analyse des données météorologiques par pays et par région,
compare les tendances climatiques, détecte les anomalies et évalue
l'impact du réchauffement climatique via des visualisations interactives.

3 pages :
    /            -> Carte Mondiale (choroplèthe + zoom régional)
    /analyse      -> Analyse climatique, anomalies, recommandations, prédiction J+1
    /dashboard    -> Indicateurs clés, tendances, export CSV
"""
from flask import Flask, render_template, request, Response
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import plot as plotly_div

from services import (
    charger_donnees, calculer_humidex, analyser_anomalies, carte_couleur_type,
)
from scripts.regions_config import liste_pays, liste_regions, PAYS_REGIONS

app = Flask(__name__)


def _fig_to_div(fig, hauteur=480):
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=hauteur)
    return plotly_div(fig, output_type="div", include_plotlyjs="cdn", config={"responsive": True})


# ----------------------------------------------------------------------------
# Page 1 : Carte Mondiale
# ----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def carte_mondiale():
    df = charger_donnees()
    if df.empty:
        return render_template("carte.html", erreur="Aucune donnée disponible pour le moment.",
                                liste_pays=liste_pays())

    df_dernier = df.sort_values("date_climat").groupby(["pays", "region"], as_index=False).last()
    df_pays = df_dernier.groupby(["pays", "iso3"], as_index=False).agg(
        temperature_moy=("temperature", "mean"),
        humidite_moy=("humidite", "mean"),
        nb_regions=("region", "nunique"),
    )

    fig_monde = px.choropleth(
        df_pays, locations="iso3", color="temperature_moy", hover_name="pays",
        hover_data={"iso3": False, "temperature_moy": ":.1f", "humidite_moy": ":.1f", "nb_regions": True},
        color_continuous_scale="RdYlBu_r",
        labels={"temperature_moy": "Température moyenne (°C)"},
        projection="natural earth",
    )
    div_monde = _fig_to_div(fig_monde, hauteur=520)

    pays_choisi = request.args.get("pays", liste_pays()[0])
    df_regions_pays = df_dernier[df_dernier["pays"] == pays_choisi]

    div_regions = None
    if not df_regions_pays.empty:
        centre_lat, centre_lon = PAYS_REGIONS[pays_choisi]["centre"]
        fig_regions = go.Figure()
        fig_regions.add_trace(go.Scattergeo(
            lon=df_regions_pays["longitude"], lat=df_regions_pays["latitude"],
            text=df_regions_pays.apply(
                lambda r: f"{r['region']}<br>{r['temperature']:.1f} °C — {r['humidite']:.0f}% humidité", axis=1
            ),
            mode="markers+text", textposition="top center",
            marker=dict(size=18, color=df_regions_pays["temperature"], colorscale="RdYlBu_r",
                        colorbar=dict(title="°C"), line=dict(width=1, color="white")),
        ))
        fig_regions.update_layout(geo=dict(
            scope="world", center=dict(lat=centre_lat, lon=centre_lon),
            projection_scale=5, showcountries=True, showcoastlines=True, bgcolor="rgba(0,0,0,0)",
        ))
        div_regions = _fig_to_div(fig_regions, hauteur=460)

    tableau_regions = df_regions_pays[
        ["region", "temperature", "temperature_predite", "humidite", "precipitations"]
    ].to_dict("records") if not df_regions_pays.empty else []

    return render_template(
        "carte.html",
        liste_pays=liste_pays(), pays_selectionne=pays_choisi,
        div_monde=div_monde, div_regions=div_regions, tableau_regions=tableau_regions,
    )


# ----------------------------------------------------------------------------
# Page 2 : Analyse & Prédictions
# ----------------------------------------------------------------------------
@app.route("/analyse", methods=["GET"])
def analyse_predictions():
    liste_p = liste_pays()
    pays_choisi = request.args.get("pays", liste_p[0])
    region_choisie = request.args.get("region", "toutes")
    regions_dispo = liste_regions(pays_choisi)

    region_filtre = None if region_choisie == "toutes" else region_choisie
    df = charger_donnees(pays=pays_choisi, region=region_filtre)

    if df.empty:
        return render_template("analyse.html", erreur="Aucune donnée disponible pour cette sélection.",
                                liste_pays=liste_p, regions_dispo=regions_dispo,
                                pays_selectionne=pays_choisi, region_selectionnee=region_choisie)

    df = df.sort_values("date_climat")
    df["date_climat"] = pd.to_datetime(df["date_climat"], unit="s")

    contexte = dict(
        liste_pays=liste_p, regions_dispo=regions_dispo,
        pays_selectionne=pays_choisi, region_selectionnee=region_choisie,
    )

    if region_filtre:
        derniere = df.iloc[-1]
        temp_actuelle = float(derniere["temperature"])
        temp_predite = float(derniere["temperature_predite"])
        humidite = float(df["humidite"].mean())
        precipitations = float(df["precipitations"].sum())
        humidex = calculer_humidex(temp_actuelle, humidite)

        anomalies = [
            {"type": t, "titre": titre, "texte": texte, "couleur": carte_couleur_type(t)}
            for t, titre, texte in analyser_anomalies(temp_actuelle, humidite, precipitations)
        ]

        fig = px.line(df, x="date_climat", y=["temperature", "temperature_predite"],
                      labels={"value": "Température (°C)", "date_climat": "Date", "variable": "Indicateur"},
                      color_discrete_sequence=["#1E3A8A", "#EF4444"])
        contexte.update(
            vue="detail", temp_actuelle=round(temp_actuelle, 1), temp_predite=round(temp_predite, 1),
            humidite=round(humidite, 1), humidex=humidex, anomalies=anomalies,
            div_chart=_fig_to_div(fig, hauteur=400),
        )
    else:
        df_dernier = df.groupby("region", as_index=False).last()
        lignes = []
        details = []
        for _, row in df_dernier.iterrows():
            df_region = df[df["region"] == row["region"]]
            humidite_moy = float(df_region["humidite"].mean())
            precip_totale = float(df_region["precipitations"].sum())
            anomalies_region = analyser_anomalies(float(row["temperature"]), humidite_moy, precip_totale)
            statut = "✅ Stable" if anomalies_region[0][0] == "succes" else " / ".join(a[1] for a in anomalies_region)
            lignes.append({
                "region": row["region"],
                "temperature": round(float(row["temperature"]), 1),
                "temperature_predite": round(float(row["temperature_predite"]), 1),
                "humidite": round(humidite_moy, 1),
                "statut": statut,
            })
            details.append({
                "region": row["region"],
                "temperature": round(float(row["temperature"]), 1),
                "anomalies": [
                    {"type": t, "titre": titre, "texte": texte, "couleur": carte_couleur_type(t)}
                    for t, titre, texte in anomalies_region
                ],
            })
        contexte.update(vue="consolide", tableau=lignes, details=details)

    return render_template("analyse.html", **contexte)


# ----------------------------------------------------------------------------
# Page 3 : Dashboard
# ----------------------------------------------------------------------------
@app.route("/dashboard", methods=["GET"])
def dashboard():
    liste_p = liste_pays()
    pays_choisi = request.args.get("pays", liste_p[0])
    region_choisie = request.args.get("region", "toutes")
    regions_dispo = liste_regions(pays_choisi)
    region_filtre = None if region_choisie == "toutes" else region_choisie

    df = charger_donnees(pays=pays_choisi, region=region_filtre)
    if df.empty:
        return render_template("dashboard.html", erreur="Aucune donnée disponible.",
                                liste_pays=liste_p, regions_dispo=regions_dispo,
                                pays_selectionne=pays_choisi, region_selectionnee=region_choisie)

    df = df.sort_values("date_climat")
    df["date_climat"] = pd.to_datetime(df["date_climat"], unit="s")
    derniere = df.iloc[-1]
    temp_actuelle = float(derniere["temperature"])
    temp_predite = float(derniere["temperature_predite"])
    humidite_moy = float(df["humidite"].mean())
    precip_totale = float(df["precipitations"].sum())
    humidex = calculer_humidex(temp_actuelle, humidite_moy)

    fig_ligne = px.line(df, x="date_climat", y=["temperature", "temperature_predite"],
                         color_discrete_sequence=["#1E3A8A", "#EF4444"],
                         labels={"value": "Température (°C)", "date_climat": "Date", "variable": "Indicateur"})
    fig_barres = px.bar(df.tail(10), x="date_climat", y="precipitations",
                         color_discrete_sequence=["#3B82F6"],
                         labels={"precipitations": "Précipitations (mm)", "date_climat": "Date"})

    colonnes = ["date_climat", "pays", "region", "temperature", "temperature_predite", "humidite", "precipitations"]
    colonnes = [c for c in colonnes if c in df.columns]

    df_affichage = df[colonnes].copy()
    if "date_climat" in df_affichage.columns:
        df_affichage["date_climat"] = df_affichage["date_climat"].dt.strftime("%d/%m/%Y")

    return render_template(
        "dashboard.html",
        liste_pays=liste_p, regions_dispo=regions_dispo,
        pays_selectionne=pays_choisi, region_selectionnee=region_choisie,
        temp_actuelle=round(temp_actuelle, 1), temp_predite=round(temp_predite, 1),
        humidite_moy=round(humidite_moy, 1), precip_totale=round(precip_totale, 1), humidex=humidex,
        div_ligne=_fig_to_div(fig_ligne, hauteur=380), div_barres=_fig_to_div(fig_barres, hauteur=380),
        tableau=df_affichage.to_dict("records"),
    )


@app.route("/dashboard/export.csv", methods=["GET"])
def exporter_csv():
    pays_choisi = request.args.get("pays")
    region_choisie = request.args.get("region", "toutes")
    region_filtre = None if region_choisie == "toutes" else region_choisie

    df = charger_donnees(pays=pays_choisi, region=region_filtre)
    colonnes = ["date_climat", "pays", "region", "temperature", "temperature_predite", "humidite", "precipitations"]
    colonnes = [c for c in colonnes if c in df.columns]

    df_export = df[colonnes].sort_values("date_climat").copy()
    if "date_climat" in df_export.columns:
        df_export["date_climat"] = pd.to_datetime(df_export["date_climat"], unit="s").dt.strftime("%d/%m/%Y")

    csv_data = df_export.to_csv(index=False)
    return Response(
        csv_data, mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=luca_donnees_{pays_choisi}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
