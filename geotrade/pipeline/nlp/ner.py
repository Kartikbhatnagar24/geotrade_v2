"""
pipeline/nlp/ner.py
────────────────────
Country name extraction using keyword matching with a
comprehensive geo-reference table (name → lat, lon, ISO).
"""

import re

# ── Geo reference: keyword → (lat, lon, ISO-2) ───────────────
# Covers countries, regions, and conflict zones commonly
# mentioned in geopolitical news.
GEO_REF: dict[str, tuple[float, float, str]] = {
    "russia":                    (55.75,   37.62,   "RU"),
    "ukraine":                   (50.45,   30.52,   "UA"),
    "united states":             (38.89,  -77.03,   "US"),
    "usa":                       (38.89,  -77.03,   "US"),
    "america":                   (38.89,  -77.03,   "US"),
    "china":                     (39.91,  116.39,   "CN"),
    "taiwan":                    (25.04,  121.56,   "TW"),
    "north korea":               (39.02,  125.75,   "KP"),
    "south korea":               (37.57,  126.98,   "KR"),
    "israel":                    (31.77,   35.22,   "IL"),
    "iran":                      (35.69,   51.42,   "IR"),
    "palestin":                  (31.92,   35.20,   "PS"),
    "gaza":                      (31.53,   34.47,   "PS"),
    "hamas":                     (31.53,   34.47,   "PS"),
    "houthi":                    (15.35,   44.21,   "YE"),
    "india":                     (28.61,   77.21,   "IN"),
    "pakistan":                  (33.72,   73.06,   "PK"),
    "afghanistan":               (34.52,   69.18,   "AF"),
    "iraq":                      (33.34,   44.39,   "IQ"),
    "syria":                     (33.51,   36.29,   "SY"),
    "turkey":                    (39.93,   32.86,   "TR"),
    "saudi arabia":              (24.69,   46.72,   "SA"),
    "yemen":                     (15.35,   44.21,   "YE"),
    "myanmar":                   (19.75,   96.09,   "MM"),
    "ethiopia":                  ( 9.03,   38.74,   "ET"),
    "somalia":                   ( 2.05,   45.34,   "SO"),
    "nigeria":                   ( 9.07,    7.40,   "NG"),
    "sudan":                     (15.55,   32.53,   "SD"),
    "venezuela":                 (10.49,  -66.88,   "VE"),
    "brazil":                    (-15.78, -47.93,   "BR"),
    "argentina":                 (-34.60, -58.38,   "AR"),
    "colombia":                  ( 4.71,  -74.07,   "CO"),
    "japan":                     (35.68,  139.69,   "JP"),
    "germany":                   (52.52,   13.40,   "DE"),
    "france":                    (48.85,    2.35,   "FR"),
    "united kingdom":            (51.51,   -0.12,   "GB"),
    "uk":                        (51.51,   -0.12,   "GB"),
    "britain":                   (51.51,   -0.12,   "GB"),
    "nato":                      (50.87,    4.43,   "BE"),
    "poland":                    (52.23,   21.01,   "PL"),
    "finland":                   (60.17,   24.94,   "FI"),
    "sweden":                    (59.33,   18.07,   "SE"),
    "greece":                    (37.98,   23.73,   "GR"),
    "serbia":                    (44.80,   20.47,   "RS"),
    "kosovo":                    (42.67,   21.17,   "XK"),
    "egypt":                     (30.04,   31.24,   "EG"),
    "libya":                     (32.88,   13.17,   "LY"),
    "mali":                      (12.65,   -8.00,   "ML"),
    "congo":                     (-4.32,   15.32,   "CD"),
    "mozambique":                (-25.97,  32.59,   "MZ"),
    "chad":                      (12.11,   15.05,   "TD"),
    "haiti":                     (18.54,  -72.34,   "HT"),
    "cuba":                      (23.13,  -82.38,   "CU"),
    "mexico":                    (19.43,  -99.13,   "MX"),
    "indonesia":                 (-6.21,  106.85,   "ID"),
    "philippines":               (14.60,  120.98,   "PH"),
    "bangladesh":                (23.72,   90.41,   "BD"),
    "azerbaijan":                (40.41,   49.87,   "AZ"),
    "armenia":                   (40.18,   44.51,   "AM"),
    "belarus":                   (53.90,   27.56,   "BY"),
    "georgia":                   (41.69,   44.83,   "GE"),
    "algeria":                   (36.74,    3.06,   "DZ"),
    "morocco":                   (33.99,   -6.85,   "MA"),
    "lebanon":                   (33.89,   35.50,   "LB"),
    "jordan":                    (31.95,   35.93,   "JO"),
    "qatar":                     (25.29,   51.53,   "QA"),
    "red sea":                   (15.00,   42.00,   "YE"),
    "crimea":                    (44.95,   34.10,   "UA"),
    "taiwan strait":             (24.00,  119.50,   "TW"),
}


def extract_countries(text: str) -> list[dict]:
    """
    Scan text for country keywords and return unique matches as:
    [{"name": str, "lat": float, "lon": float, "iso": str}, ...]
    """
    text_lower = text.lower()
    found: list[dict] = []
    seen_isos: set[str] = set()

    for keyword, (lat, lon, iso) in GEO_REF.items():
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text_lower) and iso not in seen_isos:
            seen_isos.add(iso)
            found.append({
                "name": keyword.title(),
                "lat":  lat,
                "lon":  lon,
                "iso":  iso,
            })

    return found
