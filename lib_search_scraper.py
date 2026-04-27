"""
Phoenix Public Library Catalog Scraper
Searches by title keyword across selected material types, returns only items
where the keyword appears in the actual title.

Usage:
    python scraper.py --keywords keywords.txt --output results.csv
"""

import argparse
import csv
import math
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://catalog.phoenixpubliclibrary.org"
SEARCH_URL = f"{BASE_URL}/search/searchresults.aspx"
AJAX_URL = f"{BASE_URL}/search/components/ajaxResults.aspx"
RESULTS_PER_PAGE = 100
REQUEST_DELAY = 0.5  # seconds between requests, be polite

# ---------------------------------------------------------------------------
# MATERIAL TYPE FILTER
# The catalog exposes a "limit" parameter (MAT=<id>) that filters by format.
# Each entry below is one search pass. To add or remove a format type, just
# comment out / uncomment the corresponding line — no other code changes needed.
#
# Full list of available types from the catalog's search form:
#   MAT=1   Book
#   MAT=3   Book on CD
#   MAT=4   Book on MP3
#   MAT=34  Downloadable eAudio Book   ← default (audiobooks only)
#   MAT=35  Downloadable eBook
#   MAT=7   DVD
#   MAT=19  Music CD
#   MAT=46  Streaming Audiobook        ← default (audiobooks only)
#   MAT=51  Streaming Music
#   MAT=*   All Materials (removes filter entirely)
# ---------------------------------------------------------------------------
MATERIAL_TYPES: dict[str, str] = {
    "MAT=34": "Downloadable eAudio Book",
    "MAT=46": "Streaming Audiobook",
    # "MAT=1":  "Book",           # uncomment to include physical books
    # "MAT=35": "Downloadable eBook",  # uncomment to include ebooks
    # "MAT=*":  "All Materials",  # uncomment to disable format filter entirely
}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    session.get(f"{BASE_URL}/search/", timeout=15)
    return session


def init_search(session: requests.Session, keyword: str, mat_filter: str) -> int:
    """Trigger a filtered search and return total result count."""
    r = session.get(
        SEARCH_URL,
        params={
            "type": "Keyword",
            "term": keyword,
            "by": "TI",
            "sort": "RELEVANCE",
            "limit": mat_filter,
            "page": "0",
        },
        timeout=15,
    )
    r.raise_for_status()

    ajax_r = session.get(AJAX_URL, params={"page": "1", "hpp": str(RESULTS_PER_PAGE)}, timeout=15)
    ajax_r.raise_for_status()

    soup = BeautifulSoup(ajax_r.text, "html.parser")
    count_div = soup.select_one(".c-results-utility-result-count")
    if not count_div:
        return 0

    text = count_div.get_text()
    match = re.search(r"of\s+([\d,]+)", text)
    if not match:
        return 0

    return int(match.group(1).replace(",", ""))


def fetch_page(session: requests.Session, page: int) -> list[tuple[str, str]]:
    """Fetch one AJAX result page, return list of (title, author) tuples."""
    r = session.get(AJAX_URL, params={"page": str(page), "hpp": str(RESULTS_PER_PAGE)}, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    title_groups = soup.select(".nsm-brief-primary-title-group")
    author_groups = soup.select(".nsm-brief-primary-author-group")

    results = []
    for i, title_el in enumerate(title_groups):
        link = title_el.find("a", class_="nsm-brief-action-link")
        if not link:
            continue
        # separator=" " preserves spaces between highlighted keyword spans
        title = re.sub(r" +", " ", link.get_text(separator=" ", strip=True))

        author = ""
        if i < len(author_groups):
            browse_span = author_groups[i].find("span", class_="nsm-browse-text")
            if browse_span:
                raw = browse_span.get_text(strip=True)
                # Remove trailing ", author." suffix the site adds
                author = re.sub(r",?\s*author\.?\s*$", "", raw, flags=re.IGNORECASE).strip()
                author = author.rstrip(",").strip()

        results.append((title, author))

    return results


def keyword_in_title(keyword: str, title: str) -> bool:
    """Return True if every word in the keyword phrase appears in the title."""
    title_lower = title.lower()
    if keyword.lower() in title_lower:
        return True
    # Multi-word keywords: all individual words must be present
    words = keyword.lower().split()
    return all(w in title_lower for w in words)


def scrape_keyword_for_type(
    keyword: str,
    mat_filter: str,
    format_label: str,
    verbose: bool = True,
) -> list[tuple[str, str, str, str]]:
    """
    Search the catalog for one keyword + one material type.
    Returns list of (keyword, title, author, format) rows.
    """
    if verbose:
        print(f"  [{format_label}] Searching...")

    session = make_session()
    total = init_search(session, keyword, mat_filter)

    if total == 0:
        if verbose:
            print(f"  [{format_label}] No results.")
        return []

    total_pages = math.ceil(total / RESULTS_PER_PAGE)
    if verbose:
        print(f"  [{format_label}] {total} results, {total_pages} pages — filtering by title...")

    matched = []
    for page in range(1, total_pages + 1):
        if verbose and page % 10 == 0:
            print(f"  [{format_label}] Page {page}/{total_pages}...")

        try:
            rows = fetch_page(session, page)
        except requests.RequestException as e:
            print(f"  [{format_label}] Error on page {page}: {e}", file=sys.stderr)
            break

        for title, author in rows:
            if keyword_in_title(keyword, title):
                matched.append((keyword, title, author, format_label))

        time.sleep(REQUEST_DELAY)

    if verbose:
        print(f"  [{format_label}] Done — {len(matched)} matches.")

    return matched


def scrape_keyword(keyword: str, verbose: bool = True) -> list[tuple[str, str, str, str]]:
    """
    Run one search pass per enabled material type and combine results.
    Returns list of (keyword, title, author, format) rows.
    """
    if verbose:
        print(f"\n[{keyword}] Starting ({len(MATERIAL_TYPES)} format type(s))...")

    all_rows: list[tuple[str, str, str, str]] = []
    for mat_filter, format_label in MATERIAL_TYPES.items():
        rows = scrape_keyword_for_type(keyword, mat_filter, format_label, verbose)
        all_rows.extend(rows)

    if verbose:
        print(f"[{keyword}] Total matches: {len(all_rows)}")

    return all_rows


def main():
    parser = argparse.ArgumentParser(description="Phoenix Public Library title keyword scraper")
    parser.add_argument("--keywords", required=True, help="Text file with one keyword per line")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    args = parser.parse_args()

    with open(args.keywords, encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    if not keywords:
        print("No keywords found in input file.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(keywords)} keyword(s): {keywords}")
    print(f"Format filter: {list(MATERIAL_TYPES.values())}")

    all_results: list[tuple[str, str, str, str]] = []
    for kw in keywords:
        rows = scrape_keyword(kw)
        all_results.extend(rows)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Keyword", "Title", "Author", "Format"])
        writer.writerows(all_results)

    print(f"\nTotal matches written: {len(all_results)}")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
