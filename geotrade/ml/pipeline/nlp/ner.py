"""
pipeline/nlp/ner.py
────────────────────
Country name extraction using keyword matching with a
comprehensive geo-reference table (name → lat, lon, ISO).

Improvements over v1:
  - GEO_REF expanded from ~70 → 130+ entries covering all major conflict zones,
    African nations, South/Southeast Asian countries, and relevant regions
  - extract_countries() no longer falls back to "WLD" — returns empty list if
    no match found (callers handle this gracefully)
  - Added intensity_score() to assess severity of individual articles
    based on high-signal keywords (nuclear, invasion, massacre, etc.)
"""

import re

# ── Geo reference: keyword → (lat, lon, ISO-2) ───────────────
# 130+ entries covering all active conflict zones and geopolitically
# relevant countries, cities, actors, and regions.

GEO_REF: dict[str, tuple[float, float, str]] = {
    # ── Major Powers ─────────────────────────────────────────
    "russia":               (55.75,   37.62,  "RU"),
    "kremlin":              (55.75,   37.62,  "RU"),
    "moscow":               (55.75,   37.62,  "RU"),
    "ukraine":              (50.45,   30.52,  "UA"),
    "kyiv":                 (50.45,   30.52,  "UA"),
    "united states":        (38.89,  -77.03,  "US"),
    "usa":                  (38.89,  -77.03,  "US"),
    "america":              (38.89,  -77.03,  "US"),
    "washington":           (38.89,  -77.03,  "US"),
    "pentagon":             (38.89,  -77.03,  "US"),
    "china":                (39.91,  116.39,  "CN"),
    "beijing":              (39.91,  116.39,  "CN"),

    # ── East Asia ─────────────────────────────────────────────
    "taiwan":               (25.04,  121.56,  "TW"),
    "taipei":               (25.04,  121.56,  "TW"),
    "taiwan strait":        (24.00,  119.50,  "TW"),
    "north korea":          (39.02,  125.75,  "KP"),
    "pyongyang":            (39.02,  125.75,  "KP"),
    "dprk":                 (39.02,  125.75,  "KP"),
    "south korea":          (37.57,  126.98,  "KR"),
    "seoul":                (37.57,  126.98,  "KR"),
    "japan":                (35.68,  139.69,  "JP"),
    "tokyo":                (35.68,  139.69,  "JP"),

    # ── Southeast Asia ────────────────────────────────────────
    "myanmar":              (19.75,   96.09,  "MM"),
    "burma":                (19.75,   96.09,  "MM"),
    "philippines":          (14.60,  120.98,  "PH"),
    "manila":               (14.60,  120.98,  "PH"),
    "indonesia":            (-6.21,  106.85,  "ID"),
    "jakarta":              (-6.21,  106.85,  "ID"),
    "vietnam":              (21.03,  105.84,  "VN"),
    "hanoi":                (21.03,  105.84,  "VN"),
    "thailand":             (13.75,  100.52,  "TH"),
    "malaysia":             ( 3.14,  101.69,  "MY"),
    "cambodia":             (11.57,  104.92,  "KH"),
    "singapore":            ( 1.35,  103.82,  "SG"),
    "laos":                 (17.96,  102.62,  "LA"),
    "timor-leste":          (-8.56,  125.58,  "TL"),
    "south china sea":      (12.00,  114.00,  "PH"),

    # ── South Asia ────────────────────────────────────────────
    "india":                (28.61,   77.21,  "IN"),
    "new delhi":            (28.61,   77.21,  "IN"),
    "pakistan":             (33.72,   73.06,  "PK"),
    "islamabad":            (33.72,   73.06,  "PK"),
    "kashmir":              (34.10,   74.80,  "IN"),
    "afghanistan":          (34.52,   69.18,  "AF"),
    "kabul":                (34.52,   69.18,  "AF"),
    "taliban":              (34.52,   69.18,  "AF"),
    "bangladesh":           (23.72,   90.41,  "BD"),
    "dhaka":                (23.72,   90.41,  "BD"),
    "sri lanka":            ( 6.92,   79.86,  "LK"),
    "nepal":                (27.71,   85.32,  "NP"),
    "kathmandu":            (27.71,   85.32,  "NP"),
    "mongolia":             (47.91,  106.88,  "MN"),
    "ulaanbaatar":          (47.91,  106.88,  "MN"),

    # ── Middle East ───────────────────────────────────────────
    "israel":               (31.77,   35.22,  "IL"),
    "tel aviv":             (32.06,   34.78,  "IL"),
    "iran":                 (35.69,   51.42,  "IR"),
    "tehran":               (35.69,   51.42,  "IR"),
    "palestin":             (31.92,   35.20,  "PS"),
    "gaza":                 (31.53,   34.47,  "PS"),
    "hamas":                (31.53,   34.47,  "PS"),
    "west bank":            (32.00,   35.25,  "PS"),
    "hezbollah":            (33.89,   35.50,  "LB"),
    "lebanon":              (33.89,   35.50,  "LB"),
    "beirut":               (33.89,   35.50,  "LB"),
    "houthi":               (15.35,   44.21,  "YE"),
    "yemen":                (15.35,   44.21,  "YE"),
    "sanaa":                (15.35,   44.21,  "YE"),
    "saudi arabia":         (24.69,   46.72,  "SA"),
    "riyadh":               (24.69,   46.72,  "SA"),
    "iraq":                 (33.34,   44.39,  "IQ"),
    "baghdad":              (33.34,   44.39,  "IQ"),
    "syria":                (33.51,   36.29,  "SY"),
    "damascus":             (33.51,   36.29,  "SY"),
    "jordan":               (31.95,   35.93,  "JO"),
    "qatar":                (25.29,   51.53,  "QA"),
    "doha":                 (25.29,   51.53,  "QA"),
    "uae":                  (24.46,   54.37,  "AE"),
    "united arab emirates": (24.46,   54.37,  "AE"),
    "kuwait":               (29.37,   47.98,  "KW"),
    "bahrain":              (26.23,   50.59,  "BH"),
    "red sea":              (15.00,   42.00,  "YE"),

    # ── Europe ────────────────────────────────────────────────
    "nato":                 (50.87,    4.43,  "BE"),
    "brussels":             (50.85,    4.35,  "BE"),
    "belgium":              (50.85,    4.35,  "BE"),
    "germany":              (52.52,   13.40,  "DE"),
    "berlin":               (52.52,   13.40,  "DE"),
    "france":               (48.85,    2.35,  "FR"),
    "paris":                (48.85,    2.35,  "FR"),
    "united kingdom":       (51.51,   -0.12,  "GB"),
    "uk":                   (51.51,   -0.12,  "GB"),
    "britain":              (51.51,   -0.12,  "GB"),
    "london":               (51.51,   -0.12,  "GB"),
    "poland":               (52.23,   21.01,  "PL"),
    "warsaw":               (52.23,   21.01,  "PL"),
    "finland":              (60.17,   24.94,  "FI"),
    "sweden":               (59.33,   18.07,  "SE"),
    "spain":                (40.42,   -3.70,  "ES"),
    "madrid":               (40.42,   -3.70,  "ES"),
    "italy":                (41.90,   12.50,  "IT"),
    "rome":                 (41.90,   12.50,  "IT"),
    "netherlands":          (52.37,    4.90,  "NL"),
    "amsterdam":            (52.37,    4.90,  "NL"),
    "switzerland":          (46.95,    7.45,  "CH"),
    "bern":                 (46.95,    7.45,  "CH"),
    "portugal":             (38.72,   -9.14,  "PT"),
    "lisbon":               (38.72,   -9.14,  "PT"),
    "austria":              (48.21,   16.37,  "AT"),
    "vienna":               (48.21,   16.37,  "AT"),
    "czech":                (50.08,   14.44,  "CZ"),
    "prague":               (50.08,   14.44,  "CZ"),
    "denmark":              (55.68,   12.57,  "DK"),
    "copenhagen":           (55.68,   12.57,  "DK"),
    "norway":               (59.91,   10.75,  "NO"),
    "oslo":                 (59.91,   10.75,  "NO"),
    "romania":              (44.43,   26.10,  "RO"),
    "bucharest":            (44.43,   26.10,  "RO"),
    "greece":               (37.98,   23.73,  "GR"),
    "turkey":               (39.93,   32.86,  "TR"),
    "ankara":               (39.93,   32.86,  "TR"),
    "erdogan":              (39.93,   32.86,  "TR"),
    "serbia":               (44.80,   20.47,  "RS"),
    "belgrade":             (44.80,   20.47,  "RS"),
    "kosovo":               (42.67,   21.17,  "XK"),
    "pristina":             (42.67,   21.17,  "XK"),
    "hungary":              (47.50,   19.04,  "HU"),
    "budapest":             (47.50,   19.04,  "HU"),

    # ── Post-Soviet ───────────────────────────────────────────
    "belarus":              (53.90,   27.56,  "BY"),
    "minsk":                (53.90,   27.56,  "BY"),
    "lukashenko":           (53.90,   27.56,  "BY"),
    "georgia":              (41.69,   44.83,  "GE"),
    "tbilisi":              (41.69,   44.83,  "GE"),
    "armenia":              (40.18,   44.51,  "AM"),
    "yerevan":              (40.18,   44.51,  "AM"),
    "azerbaijan":           (40.41,   49.87,  "AZ"),
    "baku":                 (40.41,   49.87,  "AZ"),
    "karabakh":             (40.00,   46.75,  "AZ"),
    "moldova":              (47.00,   28.85,  "MD"),
    "transnistria":         (47.00,   29.50,  "MD"),
    "kazakhstan":           (51.18,   71.45,  "KZ"),
    "uzbekistan":           (41.30,   69.24,  "UZ"),
    "tajikistan":           (38.56,   68.77,  "TJ"),
    "kyrgyzstan":           (42.87,   74.60,  "KG"),
    "turkmenistan":         (37.95,   58.38,  "TM"),

    # ── Africa — North ────────────────────────────────────────
    "algeria":              (36.74,    3.06,  "DZ"),
    "morocco":              (33.99,   -6.85,  "MA"),
    "libya":                (32.88,   13.17,  "LY"),
    "tripoli":              (32.88,   13.17,  "LY"),
    "egypt":                (30.04,   31.24,  "EG"),
    "cairo":                (30.04,   31.24,  "EG"),
    "tunisia":              (36.82,   10.17,  "TN"),

    # ── Africa — Sahel & West ─────────────────────────────────
    "mali":                 (12.65,   -8.00,  "ML"),
    "bamako":               (12.65,   -8.00,  "ML"),
    "burkina faso":         (12.37,   -1.53,  "BF"),
    "ouagadougou":          (12.37,   -1.53,  "BF"),
    "niger":                (13.51,    2.12,  "NE"),
    "niamey":               (13.51,    2.12,  "NE"),
    "chad":                 (12.11,   15.05,  "TD"),
    "senegal":              (14.69,  -17.44,  "SN"),
    "guinea":               ( 9.54,  -13.68,  "GN"),
    "nigeria":              ( 9.07,    7.40,  "NG"),
    "abuja":                ( 9.07,    7.40,  "NG"),
    "boko haram":           ( 9.07,    7.40,  "NG"),
    "cameroon":             ( 3.85,   11.50,  "CM"),

    # ── Africa — East & Horn ──────────────────────────────────
    "ethiopia":             ( 9.03,   38.74,  "ET"),
    "addis ababa":          ( 9.03,   38.74,  "ET"),
    "tigray":               (13.50,   39.50,  "ET"),
    "somalia":              ( 2.05,   45.34,  "SO"),
    "mogadishu":            ( 2.05,   45.34,  "SO"),
    "al-shabaab":           ( 2.05,   45.34,  "SO"),
    "sudan":                (15.55,   32.53,  "SD"),
    "khartoum":             (15.55,   32.53,  "SD"),
    "rsf":                  (15.55,   32.53,  "SD"),
    "south sudan":          ( 4.86,   31.60,  "SS"),
    "kenya":                (-1.29,   36.82,  "KE"),
    "eritrea":              (15.34,   38.93,  "ER"),
    "djibouti":             (11.59,   43.15,  "DJ"),

    # ── Africa — East & Horn additions ────────────────────────
    "ghana":                (  5.55,   -0.20,  "GH"),
    "accra":                (  5.55,   -0.20,  "GH"),
    "tanzania":             ( -6.17,   35.74,  "TZ"),
    "dar es salaam":        ( -6.80,   39.29,  "TZ"),
    "angola":               ( -8.84,   13.23,  "AO"),
    "luanda":               ( -8.84,   13.23,  "AO"),
    "zambia":               (-15.42,   28.28,  "ZM"),
    "malawi":               (-13.96,   33.79,  "MW"),
    "namibia":              (-22.56,   17.08,  "NA"),
    "botswana":             (-24.65,   25.91,  "BW"),
    "madagascar":           (-18.91,   47.54,  "MG"),

    # ── Africa — Central & Southern ───────────────────────────
    "congo":                (-4.32,   15.32,  "CD"),
    "drc":                  (-4.32,   15.32,  "CD"),
    "kinshasa":             (-4.32,   15.32,  "CD"),
    "goma":                 (-1.68,   29.22,  "CD"),
    "m23":                  (-1.68,   29.22,  "CD"),
    "rwanda":               (-1.94,   30.06,  "RW"),
    "kigali":               (-1.94,   30.06,  "RW"),
    "mozambique":           (-25.97,  32.59,  "MZ"),
    "zimbabwe":             (-17.83,  31.05,  "ZW"),
    "south africa":         (-25.75,  28.19,  "ZA"),

    # ── Americas ─────────────────────────────────────────────
    "canada":               (45.42,  -75.69,  "CA"),
    "canadian":             (45.42,  -75.69,  "CA"),
    "ottawa":               (45.42,  -75.69,  "CA"),
    "toronto":              (43.65,  -79.38,  "CA"),
    "venezuela":            (10.49,  -66.88,  "VE"),
    "caracas":              (10.49,  -66.88,  "VE"),
    "maduro":               (10.49,  -66.88,  "VE"),
    "colombia":             ( 4.71,  -74.07,  "CO"),
    "bogota":               ( 4.71,  -74.07,  "CO"),
    "brazil":               (-15.78, -47.93,  "BR"),
    "brasilia":             (-15.78, -47.93,  "BR"),
    "argentina":            (-34.60, -58.38,  "AR"),
    "buenos aires":         (-34.60, -58.38,  "AR"),
    "mexico":               (19.43,  -99.13,  "MX"),
    "guatemala":            (14.64,  -90.51,  "GT"),
    "honduras":             (14.07,  -87.21,  "HN"),
    "el salvador":          (13.69,  -89.19,  "SV"),
    "panama":               ( 8.99,  -79.52,  "PA"),
    "costa rica":           ( 9.93,  -84.08,  "CR"),
    "dominican republic":   (18.48,  -69.90,  "DO"),
    "haiti":                (18.54,  -72.34,  "HT"),
    "port-au-prince":       (18.54,  -72.34,  "HT"),
    "cuba":                 (23.13,  -82.38,  "CU"),
    "nicaragua":            (12.13,  -86.29,  "NI"),
    "peru":                 (-12.04, -77.03,  "PE"),
    "ecuador":              (-0.23,  -78.52,  "EC"),
    "bolivia":              (-16.50, -68.15,  "BO"),
    "chile":                (-33.46, -70.65,  "CL"),
    "uruguay":              (-34.90, -56.19,  "UY"),
    "paraguay":             (-25.29, -57.65,  "PY"),

    # ── Pacific ───────────────────────────────────────────────
    "australia":            (-35.28,  149.13,  "AU"),
    "australia's":          (-35.28,  149.13,  "AU"),
    "canberra":             (-35.28,  149.13,  "AU"),
    "sydney":               (-33.87,  151.21,  "AU"),
    "melbourne":            (-37.81,  144.96,  "AU"),
    "new zealand":          (-41.29,  174.78,  "NZ"),
    "wellington":           (-41.29,  174.78,  "NZ"),
    "fiji":                 (-18.14,  178.44,  "FJ"),

    # ── Possessive forms for top-mentioned countries ──────────
    "ukraine's":            (50.45,   30.52,  "UA"),
    "russia's":             (55.75,   37.62,  "RU"),
    "iran's":               (35.69,   51.42,  "IR"),
    "israel's":             (31.77,   35.22,  "IL"),
    "china's":              (39.91,  116.39,  "CN"),
    "canada's":             (45.42,  -75.69,  "CA"),

    # ── Disputed / Conflict zones ─────────────────────────────
    "crimea":               (44.95,   34.10,  "UA"),
    "donbas":               (48.00,   37.80,  "UA"),
    "donetsk":              (48.00,   37.80,  "UA"),
    "luhansk":              (48.57,   39.34,  "UA"),
    "zaporizhzhia":         (47.84,   35.14,  "UA"),
    "kherson":              (46.64,   32.62,  "UA"),
}


def extract_countries(text: str) -> list[dict]:
    """
    Scan text for country/city/entity keywords and return unique matches as:
    [{"name": str, "lat": float, "lon": float, "iso": str}, ...]

    Returns an empty list if no known countries are found.
    Does NOT fall back to WLD — callers should handle empty returns gracefully.
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


# ── Intensity scoring ─────────────────────────────────────────────────────────
# Scores how severe/intense an article is based on keyword presence.
# Used in Step 3 as an article weight when computing country tension scores.
# Score range: 0.0 (routine diplomatic) → 1.0 (nuclear/invasion/massacre)

_HIGH_SEVERITY: list[str] = [
    "nuclear", "ballistic missile", "icbm", "invasion", "war",
    "massacre", "genocide", "chemical weapon", "biological weapon",
    "civil war", "famine", "mass casualty", "death toll", "killed",
    "airstrike", "air strike", "bombing", "explosion", "blitz",
]

_MEDIUM_SEVERITY: list[str] = [
    "sanctions", "embargo", "conflict", "clash", "attack",
    "ceasefire", "military", "troops", "coup", "uprising",
    "hostage", "refugee", "displaced", "humanitarian crisis",
    "protest", "unrest", "arrested", "detained",
]

_LOW_SEVERITY: list[str] = [
    "diplomatic", "summit", "talks", "negotiation", "agreement",
    "election", "trade", "tariff", "dispute", "tension",
]


def intensity_score(text: str) -> float:
    """
    Compute article severity/intensity on a 0.0–1.0 scale.

    0.8–1.0 : nuclear, invasion, massacre, civil war
    0.4–0.7 : sanctions, conflict, coup, airstrike
    0.1–0.3 : diplomatic dispute, election, trade tension
    0.0     : no matching keywords
    """
    lower = text.lower()
    hits_high   = sum(1 for kw in _HIGH_SEVERITY
                      if re.search(r"\b" + re.escape(kw) + r"\b", lower))
    hits_medium = sum(1 for kw in _MEDIUM_SEVERITY
                      if re.search(r"\b" + re.escape(kw) + r"\b", lower))
    hits_low    = sum(1 for kw in _LOW_SEVERITY
                      if re.search(r"\b" + re.escape(kw) + r"\b", lower))

    raw = hits_high * 0.4 + hits_medium * 0.15 + hits_low * 0.05
    return round(min(raw, 1.0), 4)
