"""Wikipedia level-4 vital articles as plain text (MediaWiki API, plain-text extracts)."""

import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

from app.datasets.http import fetch
from app.datasets.sources import WIKIPEDIA_API, WIKIPEDIA_DIR, WIKIPEDIA_LICENSE, WIKIPEDIA_VITAL_PAGES

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.5
DROP_SECTIONS = re.compile(r"^(see also|references|notes|further reading|external links|bibliography|sources|citations)$", re.I)


def _api(**params: str) -> dict:
    time.sleep(PAUSE_SECONDS)
    query = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return json.loads(fetch(f"{WIKIPEDIA_API}?{query}"))


def vital_titles() -> list[str]:
    titles: list[str] = []
    for page in WIKIPEDIA_VITAL_PAGES:
        data = _api(action="parse", page=page, prop="links", redirects="1")
        titles.extend(link["title"] for link in data.get("parse", {}).get("links", []) if link.get("ns") == 0 and link.get("exists"))
    return list(dict.fromkeys(titles))


def _to_markup(title: str, extract: str) -> str:
    out = [f"# {title}"]
    skipping = False
    for line in extract.splitlines():
        line = line.strip()
        heading = re.match(r"^(=+)\s*(.*?)\s*=+$", line)
        if heading:
            skipping = bool(DROP_SECTIONS.match(heading.group(2)))
            if not skipping:
                out.append(f"{'#' * min(len(heading.group(1)), 6)} {heading.group(2)}")
            continue
        if line and not skipping:
            out.append(line)
    return "\n\n".join(out) + "\n"


def fetch_articles(limit: int, out_dir: Path = WIKIPEDIA_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    titles_path = out_dir / "vital_titles.json"
    if not titles_path.is_file():
        titles_path.write_text(json.dumps(vital_titles()))
    titles = json.loads(titles_path.read_text())[:limit]
    target = out_dir / "vital.jsonl"
    words = articles = 0
    with target.open("w", encoding="utf-8") as handle:
        for start, title in enumerate(titles):
            data = _api(action="query", prop="extracts", explaintext="1", exsectionformat="wiki",
                        titles=title, redirects="1")
            for page in data["query"]["pages"]:
                extract = page.get("extract") or ""
                if len(extract.split()) < 150:
                    continue
                markup = _to_markup(page["title"], extract)
                handle.write(json.dumps({"id": f"wikipedia:{page['pageid']}", "title": page["title"],
                                         "markup": markup, "terms": [], "glossary": []}, ensure_ascii=False) + "\n")
                words += len(markup.split())
                articles += 1
            if start % 200 == 0:
                logger.info("Wikipedia: %s/%s titles", start, len(titles))
    return {"source": "wikipedia", "selection": "Level-4 vital articles", "license": WIKIPEDIA_LICENSE,
            "url": "https://en.wikipedia.org/wiki/Wikipedia:Vital_articles/Level/4", "articles": articles, "words": words}
