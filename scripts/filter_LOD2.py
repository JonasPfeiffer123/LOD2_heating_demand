import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

import numpy as np

def filter_LOD2_with_OSM_and_adress():
    # Pfadangaben
    csv_file_path = 'examples/Zittau/data_input.csv'
    osm_geojson_path = 'examples/Zittau/buildings_zittau.geojson'
    lod_shapefile_path = 'examples/Zittau/lod2_33486_5636_2_sn.shp'
    output_geojson_path = 'examples/Zittau/filtered_LOD.geojson'

    # OSM-Gebäudedaten laden und nach Adressen filtern
    osm_gdf = gpd.read_file(osm_geojson_path)

    # CSV mit Adressen einlesen und eine Liste der Zieladressen erstellen
    df = pd.read_csv(csv_file_path, delimiter=';')
    df['VollständigeAdresse'] = df['Stadt'] + ', ' + df['Adresse']
    address_list = df['VollständigeAdresse'].unique().tolist()

    # Filtern der OSM-Daten basierend auf der Adressliste
    osm_gdf_filtered = osm_gdf[osm_gdf.apply(lambda x: f"{x['addr:city']}, {x['addr:street']} {x.get('addr:housenumber', '')}".strip() in address_list, axis=1)]

    # LOD-Daten laden
    lod_gdf = gpd.read_file(lod_shapefile_path)

    # Räumlichen Join durchführen, um Übereinstimmungen zu finden (nur IDs extrahieren)
    joined_gdf = gpd.sjoin(lod_gdf, osm_gdf_filtered, how='inner', predicate='intersects')

    # IDs der übereinstimmenden LOD-Objekte extrahieren
    matching_ids = joined_gdf.index.tolist()

    # Original-LOD-Daten basierend auf den extrahierten IDs filtern
    filtered_lod_gdf = lod_gdf[lod_gdf.index.isin(matching_ids)]

    # Gefilterte Daten in einer neuen geoJSON speichern
    filtered_lod_gdf.to_file(output_geojson_path, driver='GeoJSON')

def spatial_filter_with_polygon(lod_geojson_path, polygon_shapefile_path, output_geojson_path):
    # Polygon-Shapefile laden
    polygon_gdf = gpd.read_file(polygon_shapefile_path)
    # LOD-Daten laden
    lod_gdf = gpd.read_file(lod_geojson_path)

    # CRS anpassen
    polygon_gdf = polygon_gdf.to_crs(lod_gdf.crs)

    # Überprüfen der Gültigkeit und Reparieren von Polygon-Geometrien
    polygon_gdf['geometry'] = polygon_gdf['geometry'].buffer(0)

    # 2D-Geometrien oder gepufferte Version für die Identifizierung der Objekt-IDs verwenden
    lod_gdf_2d = lod_gdf.copy()
    lod_gdf_2d['geometry'] = lod_gdf_2d['geometry'].buffer(0)
    
    # Identifiziere Objekte, die vollständig innerhalb des Polygons liegen, basierend auf der 2D-Repräsentation
    ids_within_polygon = lod_gdf_2d[lod_gdf_2d.within(polygon_gdf.unary_union)]['ID'].unique()

    # Filtere die ursprünglichen LOD-Daten basierend auf den identifizierten IDs
    filtered_lod_gdf = lod_gdf[lod_gdf['ID'].isin(ids_within_polygon)]

    # Gefilterte Daten in einer neuen GeoJSON-Datei speichern
    filtered_lod_gdf.to_file(output_geojson_path, driver='GeoJSON')

def calculate_polygon_area_3d(polygon):
    """Berechnet die Fläche eines 3D-Polygons durch Zerlegung in Dreiecke."""
    if isinstance(polygon, Polygon):
        coords = list(polygon.exterior.coords)
        # Entferne den letzten Punkt, wenn er mit dem ersten identisch ist (geschlossene Polygone in Shapely).
        if coords[0] == coords[-1]:
            coords.pop()
            
        # Berechne die Fläche, indem Dreiecke verwendet werden.
        area = 0.0
        origin = coords[0]  # Wähle den ersten Punkt als Ursprung
        
        for i in range(1, len(coords) - 1):
            # Berechne die Fläche des Dreiecks, das vom Ursprung und zwei aufeinanderfolgenden Punkten gebildet wird.
            area += calculate_triangle_area_3d(origin, coords[i], coords[i+1])
            
        return area
    else:
        return None

def calculate_triangle_area_3d(p1, p2, p3):
    """Berechnet die Fläche eines Dreiecks im 3D-Raum mithilfe der Heron-Formel."""
    a = calculate_distance_3d(p1, p2)
    b = calculate_distance_3d(p2, p3)
    c = calculate_distance_3d(p3, p1)
    s = (a + b + c) / 2  # Semiperimeter
    return np.sqrt(s * (s - a) * (s - b) * (s - c))  # Heron-Formel

def calculate_distance_3d(point1, point2):
    """Berechnet die Distanz zwischen zwei Punkten im 3D-Raum."""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2 + (point1[2] - point2[2])**2)

def calculate_area_3d_for_feature(geometry):
    """Berechnet die 3D-Fläche für ein einzelnes Feature."""
    total_area = 0
    if isinstance(geometry, Polygon):
        total_area = calculate_polygon_area_3d(geometry)
    elif isinstance(geometry, MultiPolygon):
        for polygon in geometry.geoms:
            total_area += calculate_polygon_area_3d(polygon)
    return total_area

def process_lod2(file_path):
    # Lade die GeoJSON-Datei
    gdf = gpd.read_file(file_path)

    # Initialisiere ein Dictionary, um die Ergebnisse für jedes Gebäude zu speichern
    building_info = {}

    for _, row in gdf.iterrows():
        # Benutze 'ID' als Fallback, wenn 'Obj_Parent' None ist
        parent_id = row['Obj_Parent'] if row['Obj_Parent'] is not None else row['ID']
        
        if parent_id not in building_info:
            building_info[parent_id] = {'Ground': [], 'Wall': [], 'Roof': [], 'H_Traufe': None, 'H_Boden': None}

        # Extrahiere und speichere Geometrien und Höheninformationen
        if row['Geometr_3D'] in ['Ground', 'Wall', 'Roof']:
            building_info[parent_id][row['Geometr_3D']].append(row['geometry'])
        
        # Setze Höhen, falls noch nicht gesetzt oder aktualisiere, falls unterschiedlich (sollte theoretisch nicht passieren)
        if 'H_Traufe' in row and (building_info[parent_id]['H_Traufe'] is None or building_info[parent_id]['H_Traufe'] != row['H_Traufe']):
            building_info[parent_id]['H_Traufe'] = row['H_Traufe']
        if 'H_Boden' in row and (building_info[parent_id]['H_Boden'] is None or building_info[parent_id]['H_Boden'] != row['H_Boden']):
            building_info[parent_id]['H_Boden'] = row['H_Boden']

    # Berechne die Flächen und Volumina für jedes Gebäude
    for parent_id, info in building_info.items():
        info['Ground_Area'] = sum(calculate_area_3d_for_feature(geom) for geom in info['Ground'])
        info['Wall_Area'] = sum(calculate_area_3d_for_feature(geom) for geom in info['Wall'])
        info['Roof_Area'] = sum(calculate_area_3d_for_feature(geom) for geom in info['Roof'])
        h_traufe = info['H_Traufe']
        h_boden = info['H_Boden']
        info['Volume'] = (h_traufe - h_boden) * info['Ground_Area'] if h_traufe and h_boden else None

        print(f"Parent ID: {parent_id}, Ground Area: {info['Ground_Area']:.2f} m², Wall Area: {info['Wall_Area']:.2f} m², Roof Area: {info['Roof_Area']:.2f} m², Volume: {info['Volume']:.2f} m³")

    return building_info

# filter_LOD2_with_OSM_and_adress()

def run():
    # Pfadangaben
    #lod_geojson_path = 'examples/Görlitz/lod2_33498_5666_2_sn.geojson'
    lod_geojson_path = 'examples/Bautzen/lod2_33458_5668_2_sn.geojson'
    #polygon_shapefile_path = 'examples/Görlitz/Quartier_Konzept_vereinfacht.shp'
    polygon_shapefile_path = 'examples/Bautzen/filter_polygon.shp'
    #output_geojson_path = 'examples/Görlitz/filtered_LOD_quartier.geojson'
    output_geojson_path = 'examples/Bautzen/filtered_LOD_quartier.geojson'
    # Rufe die Funktion auf, um den Filterprozess zu starten
    #spatial_filter_with_polygon(lod_geojson_path, polygon_shapefile_path, output_geojson_path)

    #file_path = 'examples/Görlitz/filtered_LOD_quartier.geojson'
    file_path = 'examples/Bautzen/filtered_LOD_quartier.geojson'
    process_lod2(file_path)

# run()