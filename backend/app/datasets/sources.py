"""Public datasets used to train our own language tools. Licenses are recorded per source when fetched."""

from app.core.config import BACKEND_DIR

CORPUS_DIR = BACKEND_DIR / "data" / "corpus"
OPENSTAX_DIR = CORPUS_DIR / "openstax"
WIKIPEDIA_DIR = CORPUS_DIR / "wikipedia"
TREEBANK_DIR = CORPUS_DIR / "treebanks"
CORPUS_MANIFEST = CORPUS_DIR / "MANIFEST.json"
EXCLUSIONS_PATH = CORPUS_DIR / "excluded.json"

USER_AGENT = "SidelineThesisResearch/1.0 (Arellano University student project; offline corpus build)"

# General-education subjects that Philippine college student-athletes take (GE core and common electives).
OPENSTAX_REPOS = (
    "osbooks-psychology",
    "osbooks-introduction-sociology",
    "osbooks-introduction-philosophy",
    "osbooks-introduction-anthropology",
    "osbooks-introduction-political-science",
    "osbooks-american-government",
    "osbooks-us-history",
    "osbooks-world-history",
    "osbooks-life-liberty-and-pursuit-happiness",
    "osbooks-principles-economics-bundle",
    "osbooks-introduction-business",
    "osbooks-principles-marketing",
    "osbooks-entrepreneurship",
    "osbooks-introductory-statistics-bundle",
    "osbooks-biology-bundle",
    "osbooks-anatomy-physiology",
    "osbooks-microbiology",
    "osbooks-chemistry-bundle",
    "osbooks-astronomy",
    "osbooks-college-physics-bundle",
    "osbooks-lifespan-development",
    "osbooks-writing-guide",
    "osbooks-college-success",
)
OPENSTAX_RAW = "https://raw.githubusercontent.com/openstax/{repo}/main/{path}"

UD_TREEBANKS = {
    "en_ewt": {
        "repo": "UD_English-EWT",
        "license": "CC BY-SA 4.0",
        "citation": "Silveira et al. 2014, A Gold Standard Dependency Corpus for English (LREC); Universal Dependencies.",
    },
    "en_gum": {
        "repo": "UD_English-GUM",
        "license": "CC BY 4.0 for most genres; some sub-corpora (e.g. wikiHow) CC BY-NC-SA. See the repository LICENSE.",
        "citation": "Zeldes 2017, The GUM Corpus (Language Resources and Evaluation 51(3)); Universal Dependencies.",
    },
}
UD_RAW = "https://raw.githubusercontent.com/UniversalDependencies/{repo}/master/{name}-ud-{split}.conllu"
UD_SPLITS = ("train", "dev", "test")

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0 (Wikipedia contributors)"
# Level-4 vital articles (about 10,000 articles Wikipedia editors consider core general knowledge), without biographies.
WIKIPEDIA_VITAL_PAGES = tuple(f"Wikipedia:Vital articles/Level 4/{page}" for page in (
    "Arts", "Biology and health sciences", "Everyday life", "Geography", "History", "Mathematics",
    "Philosophy and religion", "Physical sciences", "Society and social sciences", "Technology",
))
