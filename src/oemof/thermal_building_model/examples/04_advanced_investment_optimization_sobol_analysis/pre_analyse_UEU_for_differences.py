import geopandas as gpd
# Liste der Dateipfade
paths = [
    r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New\processed_bds_in_DENI03403000SEC4580.gpkg",
    r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New\processed_bds_in_DENI03403000SEC5101.gpkg",
    r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New\processed_bds_in_DENI03403000SEC5658.gpkg"
]
# Variablen zur Speicherung der Min/Max-Werte
# Variablen zur Speicherung der Min/Max-Werte
sfh_min_floor_area = float('inf')
sfh_max_floor_area = float('-inf')
mfh_min_floor_area = float('inf')
mfh_max_floor_area = float('-inf')

sfh_min_ratio = float('inf')
sfh_max_ratio = float('-inf')
mfh_min_ratio = float('inf')
mfh_max_ratio = float('-inf')

sfh_min_residents = float('inf')
sfh_max_residents = float('-inf')
mfh_min_residents = float('inf')
mfh_max_residents = float('-inf')
# Iteriere über alle Pfade
for path in paths:
    layers = gpd.list_layers(path)
    layer_name = layers["name"].iloc[0]  # einfach den ersten nehmen
    gdf = gpd.read_file(path, layer=layer_name)
    # Iteriere durch alle Zeilen im GeoDataFrame
    for idx, row in gdf.iterrows():
        building_id = row['building_id']
        building_type = row['tabula_building_type']
        total_floor_area = row['total_floor_area']
        roof_surface_area = row['roof_surface_area']
        number_of_residents = row['number_of_residents']

        # Verhältnismäßigkeit berechnen, mit Fehlerbehandlung falls die Fläche Null ist
        if roof_surface_area != 0:
            ratio = total_floor_area / roof_surface_area
        else:
            ratio = None  # Falls die Dachfläche 0 ist, setze das Verhältnis als None

        # Auswertung der Min/Max-Werte für Floor Area und Floor-to-Roof Ratio
        if building_type == 'SFH':
            if total_floor_area < sfh_min_floor_area:
                sfh_min_floor_area = total_floor_area
            if total_floor_area > sfh_max_floor_area:
                sfh_max_floor_area = total_floor_area

            if ratio is not None:
                if ratio < sfh_min_ratio:
                    sfh_min_ratio = ratio
                if ratio > sfh_max_ratio:
                    sfh_max_ratio = ratio

            # Min/Max für number_of_residents für SFH
            if number_of_residents < sfh_min_residents:
                sfh_min_residents = number_of_residents
            if number_of_residents > sfh_max_residents:
                sfh_max_residents = number_of_residents

        elif building_type == 'MFH':
            if total_floor_area < mfh_min_floor_area:
                mfh_min_floor_area = total_floor_area
            if total_floor_area > mfh_max_floor_area:
                mfh_max_floor_area = total_floor_area

            if ratio is not None:
                if ratio < mfh_min_ratio:
                    mfh_min_ratio = ratio
                if ratio > mfh_max_ratio:
                    mfh_max_ratio = ratio

            # Min/Max für number_of_residents für MFH
            if number_of_residents < mfh_min_residents:
                mfh_min_residents = number_of_residents
            if number_of_residents > mfh_max_residents:
                mfh_max_residents = number_of_residents

# Ausgabe der Ergebnisse
print(f"SFH - Min Floor Area: {sfh_min_floor_area} m², Max Floor Area: {sfh_max_floor_area} m²")
print(f"MFH - Min Floor Area: {mfh_min_floor_area} m², Max Floor Area: {mfh_max_floor_area} m²")
print(f"SFH - Min Floor-to-Roof Ratio: {sfh_min_ratio:.2f}, Max Floor-to-Roof Ratio: {sfh_max_ratio:.2f}")
print(f"MFH - Min Floor-to-Roof Ratio: {mfh_min_ratio:.2f}, Max Floor-to-Roof Ratio: {mfh_max_ratio:.2f}")

# Ausgabe der Min/Max-Werte für number_of_residents
print(f"SFH - Min Residents: {sfh_min_residents}, Max Residents: {sfh_max_residents}")
print(f"MFH - Min Residents: {mfh_min_residents}, Max Residents: {mfh_max_residents}")