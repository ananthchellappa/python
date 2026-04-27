# How I Built a Python Scraper for Phoenix Public Library — Without a Browser

*A step-by-step guide to reverse-engineering a web app's network requests and automating library catalog searches.*

---

## The Problem

The [Phoenix Public Library catalog](https://catalog.phoenixpubliclibrary.org/search/) lets you search for books by title. But when you search for "magic" with **Search by: Title**, the results include books where "magic" only appears in the *series name* — not the actual book title. For example:

- ❌ **"A bossy bad day"** — keyword is in *Series: Williams, Zanaiah Boss Magic*
- ❌ **"Found"** — keyword is in *Series: Prineas, Sarah. Magic Thief*
- ✅ **"Magic"** — keyword IS in the actual title
- ✅ **"The Magic Tree House"** — keyword IS in the title

The manual approach: search, change results per page to 100, scroll through hundreds of pages, copy relevant rows by hand.

**The goal:** automate this — take a list of keywords, output a clean CSV of only those books where the keyword appears in the actual title.

---

## Why ChatGPT + Playwright Failed

Playwright (and Selenium) launch a real browser to click buttons and render JavaScript. For this library site, that approach breaks because:

1. The site sets session cookies on the first visit — a browser handles this automatically, but headless automation often fails to sequence it correctly.
2. The actual search results are loaded **via a hidden AJAX request**, not rendered in the initial page HTML. Playwright times out waiting for elements that load asynchronously.

The right approach: skip the browser entirely and **talk directly to the API the website already uses**.

---

## Step 1 — Understanding the Network (Browser DevTools)

Open Chrome, go to `https://catalog.phoenixpubliclibrary.org/search/`, press **F12** to open DevTools, and click the **Network** tab.

1. Type "magic" in the search box, set **Search by** to "Title", click Search.
2. Watch the Network tab. You'll see a flood of requests. Filter by **XHR/Fetch** to see only API calls.

You'll notice two important things:

**First:** The search results page URL reveals the search parameters:
```
searchresults.aspx?type=Keyword&term=magic&by=TI&sort=RELEVANCE&page=0
```
`by=TI` means "search by Title". This is the key parameter.

**Second:** The `#searchResults` div on the page starts empty with a loading spinner — results load *after* the page. Filter by XHR and you'll find a call to:
```
/search/components/ajaxResults.aspx?page=1&hpp=100
```
This is the actual endpoint that returns the HTML results fragment.

---

## Step 2 — Reverse Engineering the Session

The site uses `ASP.NET_SessionId` cookies. Without a valid session, requests redirect in a loop.

The fix: use `requests.Session()` — it automatically stores and replays cookies just like a browser.

```python
import requests

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 ..."})

# Step 1: Hit the home page to get session cookies
session.get("https://catalog.phoenixpubliclibrary.org/search/")

# Step 2: Trigger the search (this sets search state on the server)
session.get(
    "https://catalog.phoenixpubliclibrary.org/search/searchresults.aspx",
    params={"type": "Keyword", "term": "magic", "by": "TI", "sort": "RELEVANCE", "page": "0"}
)

# Step 3: NOW fetch the actual results via the AJAX endpoint
r = session.get(
    "https://catalog.phoenixpubliclibrary.org/search/components/ajaxResults.aspx",
    params={"page": "1", "hpp": "100"}
)
```

Order matters: you must visit the home page, then trigger the search, *then* call `ajaxResults.aspx`. Each step sets server-side session state the next step depends on.

---

## Step 3 — Parsing the HTML Fragment

`ajaxResults.aspx` returns an HTML fragment (not a full page). Inspect it with BeautifulSoup:

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(r.text, "html.parser")

title_groups = soup.select(".nsm-brief-primary-title-group")
author_groups = soup.select(".nsm-brief-primary-author-group")

for i, title_el in enumerate(title_groups):
    link = title_el.find("a", class_="nsm-brief-action-link")
    title = link.get_text(strip=True)

    author_span = author_groups[i].find("span", class_="nsm-browse-text")
    author = author_span.get_text(strip=True)
    # Clean up trailing ", author." suffix the site adds
    author = author.rstrip(", author.").strip()

    print(title, "|", author)
```

Key CSS classes (discovered via DevTools > Elements panel):
| Element | CSS Class |
|---|---|
| Title container | `.nsm-brief-primary-title-group` |
| Title link | `.nsm-brief-action-link` |
| Author container | `.nsm-brief-primary-author-group` |
| Author text | `.nsm-browse-text` |

---

## Step 4 — Handling Pagination

The result count lives in `.c-results-utility-result-count` and looks like "1 - 100 of 15145". Extract the total:

```python
import re, math

count_div = soup.select_one(".c-results-utility-result-count")
text = count_div.get_text()
total = int(re.search(r"of\s+([\d,]+)", text).group(1).replace(",", ""))
total_pages = math.ceil(total / 100)
```

Then loop:
```python
for page in range(1, total_pages + 1):
    r = session.get(AJAX_URL, params={"page": str(page), "hpp": "100"})
    # parse, filter, collect...
    time.sleep(0.5)  # be polite to the server
```

---

## Step 5 — The Title Filter

The library's "Search by Title" still returns items where the keyword is only in a series or subtitle field. Filter client-side:

```python
def keyword_in_title(keyword: str, title: str) -> bool:
    """True if every word of the keyword phrase appears in the title."""
    title_lower = title.lower()
    if keyword.lower() in title_lower:
        return True
    # Multi-word: all words must be present
    return all(w in title_lower for w in keyword.lower().split())
```

This correctly:
- ✅ Includes "Magic Tree House" for keyword "magic tree"
- ❌ Excludes "A bossy bad day" (series name has magic, title doesn't)

---

## Step 6 — Filtering by Material Type (Audiobooks Only)

When Ananth received the first draft of the script, he clarified: he only wanted **audiobooks** — specifically "Downloadable eAudio Book" and "Streaming Audiobook". The "magic" search returned results from books, DVDs, music CDs, e-books, and more. We needed to filter those out.

**Finding the filter parameter**

The catalog search page has a "Limit by" dropdown. Inspecting its HTML reveals the underlying `limit` query parameter:

```html
<select name="...dropdownLimitFilter">
  <option value="MAT=*">All Materials</option>
  <option value="MAT=34">Downloadable eAudio Book</option>
  <option value="MAT=46">Streaming Audiobook</option>
  ...
</select>
```

The `limit=MAT=34` parameter tells the server to return only that material type — no client-side filtering needed. This cuts the result set dramatically (15,000+ total → ~1,700 audiobooks for "magic").

**Running two searches, combining results**

Since we want both types, the script runs one search pass per material type and merges the rows:

```python
MATERIAL_TYPES = {
    "MAT=34": "Downloadable eAudio Book",
    "MAT=46": "Streaming Audiobook",
}

for mat_filter, format_label in MATERIAL_TYPES.items():
    session.get(SEARCH_URL, params={..., "limit": mat_filter, ...})
    # paginate through ajaxResults.aspx, filter by title, collect rows
```

**Toggle any format in one line**

The `MATERIAL_TYPES` dict is the only thing you need to edit. Every entry is one search pass. To add physical audiobooks on CD, for example:

```python
MATERIAL_TYPES = {
    "MAT=34": "Downloadable eAudio Book",
    "MAT=46": "Streaming Audiobook",
    "MAT=3":  "Book on CD",  # ← add this line
}
```

To disable the filter entirely and get all material types, swap in `MAT=*`:

```python
MATERIAL_TYPES = {
    "MAT=*": "All Materials",
}
```

**The `Format` column**

The CSV now includes a fourth column so you can tell the two audiobook types apart at a glance:

```
Keyword,Title,Author,Format
magic,Magic,Gosden Chris,Downloadable eAudio Book
magic,The magic thief,Prineas Sarah,Streaming Audiobook
...
```

---

## Running the Script

Install dependencies:
```bash
pip install requests beautifulsoup4
```

Create a `keywords.txt` file with one keyword per line:
```
magic
```

Run:
```bash
python scraper.py --keywords keywords.txt --output results.csv
```

Sample output (audiobooks only):
```
Keyword,Title,Author,Format
magic,Magic,Gosden Chris,Downloadable eAudio Book
magic,Black magic woman,Warren Christine,Downloadable eAudio Book
magic,The magic of Oz,Baum L. Frank,Downloadable eAudio Book
magic,The magic thief,Prineas Sarah,Streaming Audiobook
...
```

Results for "magic" with audiobook filter: **1,413 matches** (313 Downloadable + 1,100 Streaming) out of ~1,670 total audiobook results — the difference is items where "magic" appears in a series name but not the title itself.

---

## Key Takeaways

1. **Inspect XHR requests first** — most modern sites load data via AJAX, not in the initial HTML.
2. **`requests.Session()` replaces browser cookies** — it automatically handles cookie-based session state.
3. **Find the real API endpoint** — the `ajaxResults.aspx` URL was hidden in a JavaScript file (`results.js`). Searching for function names in loaded scripts reveals the real URLs.
4. **Filter client-side when needed** — the server-side search is "close enough" but not exact; a simple Python string check closes the gap.
5. **Use server-side filters when available** — the `MAT=` parameter cuts the result set before pagination, making the script faster and the output cleaner.
6. **Be polite** — `time.sleep(0.5)` between pages prevents hammering the server and getting blocked.

---

## Files

| File | Purpose |
|---|---|
| `scraper.py` | Main script — run this |
| `keywords.txt` | Input: one keyword per line |
| `results.csv` | Output: Keyword, Title, Author, Format |
| `requirements.txt` | Python dependencies |
