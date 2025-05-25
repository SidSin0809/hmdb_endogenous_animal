#!/usr/bin/env python3
"""
hmdb_endogenous_animal.py v1.0 

Objective
---------
1. **Stream‑parse** the huge `hmdb_metabolites.xml` file *without* loading it fully
   into memory and collect every `<accession>` (HMDB ID).
2. **Concurrent HTTP crawl** of the corresponding MetaboCard pages to decide
   whether the metabolite is flagged under **Source → Endogenous → Animal**.
3. Emit a TSV report `HMDB_ID\tHas_Endogenous_Animal` where the flag is `1` or
   `0`.

Design
------
* Pure‑stdlib XML parsing (no `lxml`) – works everywhere Python ≥ 3.8 is
  available.
* Simple but robust concurrency: `concurrent.futures.ThreadPoolExecutor` +
  `requests`.
* Automatic exponential back‑off & retry (up to 5 attempts) for network hiccups.
* Safe to interrupt with **Ctrl‑C**; add `--resume` to skip IDs already written
  to the output file.
* Optional progress bar if the **tqdm** package is installed – otherwise falls
  back to a plain counter.

Usage (examples)
----------------
```bash
# First run – 32 worker threads, write report
python hmdb_endogenous_animal.py hmdb_metabolites.xml --workers 32

# Resume a cancelled run, append to the same file
python hmdb_endogenous_animal.py hmdb_metabolites.xml --resume
```

Dependencies: `pip install requests tqdm`  (tqdm is optional but recommended).
"""

from __future__ import annotations

import argparse
import csv
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable
from xml.etree.ElementTree import iterparse

import requests

MAX_WORKERS_DEFAULT = 20   # simultaneous HTTP connections
MAX_RETRIES = 5
BACKOFF_FACTOR = 1.5       # seconds → 1.5, 2.25, 3.38, ...
TIMEOUT = 30               # seconds per request
HMDB_URL = "https://hmdb.ca/metabolites/{}"

# ───────────────────────────── XML parsing ──────────────────────────────── #

def extract_ids(xml_path: Path) -> list[str]:
    """Stream‑parse an HMDB XML dump and collect accession IDs."""
    ids: list[str] = []
    strip_ns = re.compile(r"\{.*?\}")

    for _event, elem in iterparse(xml_path, events=("end",)):
        tag = strip_ns.sub("", elem.tag)
        if tag == "metabolite":
            acc = elem.findtext(".//{*}accession")
            if acc:
                ids.append(acc.strip().upper())
            # release memory for finished branch
            elem.clear()
    return ids

# ───────────────────────────── Networking ───────────────────────────────── #

def fetch_page(hmdb_id: str, session: requests.Session) -> str | None:
    """GET the MetaboCard HTML with retries and exponential back‑off."""
    url = HMDB_URL.format(hmdb_id)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except KeyboardInterrupt:
            raise
        except Exception:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(BACKOFF_FACTOR ** attempt)
    return None

def has_animal_flag(html: str) -> bool:
    """Very tolerant text search for the Endogenous/Animal flag."""
    h = html.lower()
    # Make sure both keywords appear in the page – order does not matter
    return "endogenous" in h and "animal" in h

def check_id(hmdb_id: str, session: requests.Session) -> tuple[str, int]:
    html = fetch_page(hmdb_id, session)
    flag = 1 if (html and has_animal_flag(html)) else 0
    return hmdb_id, flag

# ───────────────────────────── Orchestrator ─────────────────────────────── #

def crawl(ids: Iterable[str], out_tsv: Path, resume: bool, workers: int):
    processed: set[str] = set()
    mode = "w"

    # Resume support – read existing IDs if file already exists
    if resume and out_tsv.exists():
        with open(out_tsv, newline="", encoding="utf‑8") as f:
            processed = {row[0] for row in csv.reader(f, delimiter="\t")}
        ids = [i for i in ids if i not in processed]
        mode = "a"

    with requests.Session() as sess, \
            open(out_tsv, mode, newline="", encoding="utf‑8") as fh, \
            ThreadPoolExecutor(max_workers=workers) as pool:

        writer = csv.writer(fh, delimiter="\t")
        if mode == "w":
            writer.writerow(["HMDB_ID", "Has_Endogenous_Animal"])

        futures = {pool.submit(check_id, hid, sess): hid for hid in ids}

        # Progress bar (optional)
        try:
            import tqdm  # type: ignore
            progress_iter = tqdm.tqdm(as_completed(futures), total=len(futures), desc="Crawling")
        except ModuleNotFoundError:
            progress_iter = as_completed(futures)

        for fut in progress_iter:
            hmdb_id, flag = fut.result()
            writer.writerow([hmdb_id, flag])

# ────────────────────────────── CLI entry ───────────────────────────────── #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag HMDB metabolites whose Source → Endogenous list contains 'Animal'."
    )
    parser.add_argument("xmlfile", type=Path, help="Path to hmdb_metabolites.xml")
    parser.add_argument("--out", type=Path, default=Path("hmdb_endogenous_animal.tsv"), help="Output TSV file path")
    parser.add_argument("--resume", action="store_true", help="Resume a cancelled run by appending to existing file")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS_DEFAULT, help="Number of worker threads")
    args = parser.parse_args()

    # Graceful Ctrl‑C
    signal.signal(signal.SIGINT, lambda *_: sys.exit("\nInterrupted – exiting …"))

    ids = extract_ids(args.xmlfile)
    if not ids:
        sys.exit("❌  No HMDB IDs were found – is the XML path correct?")

    crawl(ids, args.out, args.resume, max(1, args.workers))

if __name__ == "__main__":
    main()
