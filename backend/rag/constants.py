from __future__ import annotations

from core.config import env_bool, env_float, env_int

GENERAL_FACULTY_ID = "uvt"

INTENT_KEYWORDS = {
    "orar": ("orar", "orare", "program cursuri", "program seminar"),
    "burse": ("bursa", "burse", "bursier", "bursieri"),
    "contact": ("contact", "secretariat", "telefon", "email", "adresa", "program public"),
    "admitere": ("admitere", "inscriere", "inscrieri", "candidat"),
    "regulamente": (
        "regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri",
        "credite voluntariat", "credite de voluntariat", "portofoliu", "portofolii", "voluntariat",
        "acte", "documente", "documente justificative", "dosar social",
    ),
    "studenti": (
        "student", "studenti", "cazare", "camin", "camine", "taxa", "taxe", "studentweb",
        "calendar academic", "structura anului", "an universitar", "anul universitar",
        "inceperea anului", "semestru", "sesiune", "sesiuni", "vacanta", "vacante", "saptamani",
        "credite voluntariat", "credite de voluntariat", "portofoliu", "portofolii",
        "voluntariat", "acte cazare", "dosar cazare",
    ),
}

INTENT_PAGE_TYPES = {
    "orar": ("orar", "studenti", "general"),
    "burse": ("burse", "regulamente", "studenti", "general"),
    "contact": ("contact", "general"),
    "admitere": ("admitere", "regulamente", "general"),
    "regulamente": ("regulamente", "studenti", "burse", "general"),
    "studenti": ("studenti", "general", "contact"),
    "general": ("general", "studenti", "contact", "admitere", "burse", "orar", "regulamente"),
}

PAGE_HINTS = {
    "orar": ("orare", "orar"),
    "burse": ("burse", "bursa", "burselor"),
    "contact": ("contact", "secretariat"),
    "admitere": ("admitere", "inscriere"),
    "regulamente": (
        "regulamente", "regulament", "metodologie", "metodologii", "procedura", "proceduri",
        "voluntariat", "credite-voluntariat", "credite voluntariat", "documente", "acte",
    ),
    "studenti": (
        "studenti", "studentweb", "cazare", "camine", "camin", "taxe", "calendar", "structura anului",
        "semestru", "sesiune", "sesiuni", "vacanta", "vacante", "saptamani",
        "voluntariat", "credite-voluntariat", "credite voluntariat", "portofoliu", "dosar-cazare",
    ),
}

COMMON_REPLACEMENTS = (
    (r"\bfmi\b", "informatica"),
    (r"\bfac(?:ultatea)?(?:\s+de)?\s+info(?:rmatica)?\b", "informatica"),
    (r"\bmatematica\s+si\s+informatica\b", "informatica"),
    (r"\binformatici\b", "informatica"),
    (r"\binformaticii\b", "informatica"),
    (r"\binformatia\b", "informatica"),
    (r"\borr?ar(?:ul|ului)?\b", "orar"),
    (r"\borarelor\b", "orare"),
    (r"\bsecretar(?:uat|ait)\b", "secretariat"),
    (r"\bsecreteriat\b", "secretariat"),
    (r"\bsecretariatul\b", "secretariat"),
    (r"\bcamine(?:le|lor)?\b", "camine"),
    (r"\bcamin(?:ul|ului)?\b", "camin"),
    (r"\badmietere\b", "admitere"),
    (r"\badmiter[ew]\b", "admitere"),
    (r"\bburs[aeiw]\b", "burse"),
    (r"\bburselor\b", "burse"),
    (r"\bbursele\b", "burse"),
    (r"\bcumuleaz[ae]\b", "cumulare"),
    (r"\bcumulat[ae]?\b", "cumulare"),
    (r"\bdoua\b", "2"),
    (r"\bcredit(?:ele|elor|ului)?\b", "credite"),
    (r"\bdepun(?:erea|erii|e)?\b", "depune"),
    (r"\bportofoli(?:ul|ului|ile|ilor)?\b", "portofoliu"),
    (r"\bvoluntariat(?:ul|ului)?\b", "voluntariat"),
)

TOKEN_ALIASES = {
    "facultatii": "facultate",
    "facultatea": "facultate",
    "studentului": "student",
    "studentilor": "studenti",
    "burselor": "burse",
    "bursei": "bursa",
    "metodologiile": "metodologie",
    "metodologia": "metodologie",
    "regulamentul": "regulament",
    "regulamentele": "regulamente",
    "procedurile": "proceduri",
    "admiterea": "admitere",
    "inscrierea": "inscriere",
    "anul": "an",
    "beneficieze": "beneficia",
    "beneficiez": "beneficia",
    "beneficiaza": "beneficia",
    "creditul": "credite",
    "creditelor": "credite",
    "creditele": "credite",
    "cumula": "cumulare",
    "cumularea": "cumulare",
    "cumuleaza": "cumulare",
    "depunerea": "depune",
    "depunerii": "depune",
    "caminul": "camin",
    "caminului": "camin",
    "caminele": "camine",
    "caminelor": "camine",
    "portofoliile": "portofoliu",
    "portofoliilor": "portofoliu",
    "portofoliului": "portofoliu",
    "voluntariatului": "voluntariat",
    "actele": "acte",
    "documentele": "documente",
    "documentelor": "documente",
    "justificative": "justificativ",
    "parintii": "parinti",
    "parintilor": "parinti",
    "parintele": "parinte",
    "orfanii": "orfani",
    "orfanilor": "orfani",
    "monoparentale": "monoparentala",
    "divortati": "divort",
    "divortata": "divort",
    "divortat": "divort",
    "veniturilor": "venituri",
    "venitului": "venituri",
    "sociala": "social",
    "sociale": "social",
    "saptamana": "saptamani",
    "saptamanile": "saptamani",
    "saptamanilor": "saptamani",
    "semestrul": "semestru",
    "semestrului": "semestru",
    "vacanta": "vacante",
    "vacantele": "vacante",
    "vacantelor": "vacante",
}

STOPWORDS = {
    "a", "ai", "al", "ale", "am", "ar", "as", "asta", "ca", "care", "ce", "cea", "cele", "cel",
    "cei", "cum", "cu", "daca", "dar", "de", "din", "doar", "e", "este", "fi", "fie", "gasesc", "in", "la",
    "mai", "ma", "mi", "o", "pe", "pentru", "pot", "poate", "sa", "sau", "se", "si", "sunt",
    "am", "iar", "le", "nu", "cand", "spune", "spune-mi", "te", "rog", "despre", "ceva", "imi", "pt",
    "un", "unei", "unui", "unde", "vreau",
}

DOMAIN_VOCABULARY = {
    "admitere", "adresa", "anexa", "beneficia", "bursa", "burse", "candidat", "cazare",
    "acte", "adeverinta", "certificat", "certificate", "contact", "cumulare", "depune", "depunere",
    "document", "documente", "dosar", "email", "evaluare", "justificativ",
    "facultate", "formular", "informatica", "inscriere", "informatii", "informatie", "metodologie",
    "metodologii", "orar", "orare", "procedura",
    "model", "portofoliu", "portofolii", "proceduri", "proba", "program", "regulament", "regulamente",
    "raport", "recunoastere", "secretariat", "student", "studenti", "subiect", "subiecte", "voluntariat",
    "an", "calendar", "camin", "camine", "cursuri", "incepe", "inceperea", "parola", "saptamani",
    "semestru", "sesiune", "sesiuni", "studentweb", "structura", "taxa", "taxe", "telefon",
    "universitar", "uvt", "vacante", "wifi", "credit", "credite",
    "familie", "financiar", "monoparentala", "orfan", "orfani", "parinte", "parinti", "social",
    "sociale", "sprijin", "venit", "venituri", "divort", "sentinta", "deces", "intretinere",
}

POLICY_PHRASES = (
    "este posibil",
    "se poate",
    "pot beneficia",
    "poate beneficia",
    "beneficia de",
    "beneficieze de",
    "pot primi",
    "reguli",
    "conditii",
    "eligibil",
    "cumulare",
    "cumuleaza",
    "2 burse",
    "ce acte",
    "acte trebuie",
    "acte am nevoie",
    "documente justificative",
)

POLICY_DOCUMENT_TERMS = ("regulament", "metodologie", "procedura", "anexa", "hotarare")
SCHOLARSHIP_TERMS = ("bursa", "burse", "burselor", "bursieri", "sprijin financiar")
CUMULATION_TERMS = ("cumulare", "cumuleaza", "cumula", "art 5", "art. 5")
VOLUNTEERING_TERMS = ("voluntariat", "voluntar", "voluntari", "ong", "portofoliu", "portofolii")
VOLUNTEERING_CREDIT_TERMS = ("credite", "credit", "creditelor", "transferabile")
SUBMISSION_TERMS = ("depune", "depunere", "depunerea", "portofoliu", "portofolii", "formular", "dosar")
DOCUMENT_REQUEST_TERMS = (
    "acte", "document", "documente", "justificativ", "justificative", "certificat",
    "certificate", "adeverinta", "dosar", "formular",
)
SOCIAL_CONTEXT_TERMS = (
    "orfan", "orfani", "monoparentala", "monoparental", "familie", "parinte", "parinti",
    "divort", "deces", "social", "sociale", "venit", "venituri", "financiar", "intretinere",
    "handicap", "dizabilitati", "vulnerabil",
)
STRONG_SOCIAL_CONTEXT_TERMS = (
    "orfan", "orfani", "monoparentala", "monoparental", "familie", "parinte", "parinti",
    "divort", "deces", "social", "sociale", "venit", "venituri", "intretinere",
    "handicap", "dizabilitati", "vulnerabil",
)
HOUSING_TERMS = ("cazare", "camin", "camine")
ACADEMIC_CALENDAR_TERMS = (
    "calendar", "structura", "universitar", "semestru", "sesiune", "sesiuni",
    "vacante", "saptamani",
)
OFF_TOPIC_SOCIAL_POLICY_TERMS = (
    "recunoasterea-perioadelor",
    "recunoastere perioadelor",
    "mobilitate",
    "mobilitati",
    "erasmus",
    "euro-200",
    "calculator",
    "calculatoare",
    "tabere",
    "tabara",
)
VECTOR_SEARCH_LIMIT = env_int("VECTOR_SEARCH_LIMIT", "18", minimum=8)
SEMANTIC_SCORE_WEIGHT = env_float("SEMANTIC_SCORE_WEIGHT", "58")
VECTOR_LEXICAL_BACKFILL_ENABLED = env_bool("VECTOR_LEXICAL_BACKFILL_ENABLED", "false")
OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS = env_int("OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS", "8", minimum=1)
OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS = env_int("OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS", "12", minimum=4)
