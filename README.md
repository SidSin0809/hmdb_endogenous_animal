# hmdb_endogenous_animal
Fault-tolerant streaming crawler for HMDB Endogenous/Animal flags

hmdb_endogenous_animal is a single-file, fault-tolerant Python tool that streams the ~1-GB HMDB XML, extracts each <accession> on the fly, then concurrently queries every MetaboCard to see whether the compound is tagged “Endogenous → Animal,” writing a tidy TSV you can drop straight into R or Python. The design keeps memory in the low-MB range, recovers cleanly from network hiccups, and can resume mid-run.

Key Features
1] Uses xml.etree.ElementTree.iterparse so the HMDB dump is never fully loaded into RAM — ideal for big files on modest workstations.
2] A dedicated parser thread feeds a queue.Queue; a configurable swarm of ThreadPoolExecutor workers processes URLs in parallel, leveraging Python’s standard library concurrency primitives.
3] All requests are wrapped in a retry/back-off helper (built on requests + HTTPAdapter) to survive flaky institutional proxies or HMDB throttling.
4] Detects tqdm; if available, prints a dynamic progress bar, else falls back to periodic console updates.
5] --resume scans the existing TSV every 5 000 rows and skips already-done IDs, so power cuts or ^C won’t waste hours of crawling.

Quick Start
# 1. Grab the code
git clone https://github.com/SidSin0809/hmdb_endogenous_animal.git

# 2. Install minimal deps
python -m pip install -r requirements.txt     # requests tqdm

# 3. Run
python hmdb_endogenous_animal.py \
       hmdb_metabolites.xml \
       --workers 30 \
       --out endogenous_animal.tsv \
       --resume

| Flag              | Default                 | Description                                    |
| ----------------- | ----------------------- | ---------------------------------------------- |
| `--out PATH`      | `endogenous_animal.tsv` | Output file (TSV, 2 cols: ID & flag).          |
| `--workers N`     | `8`                     | Thread pool size. Tune for your bandwidth/CPU. |
| `--cutoff SECS`   | `10`                    | Per-request timeout.                           |
| `--max-retries N` | `5`                     | Total retries before declaring a URL dead.     |
| `--resume`        | off                     | Skip IDs already in the output file.           |

Citing This Tool
Singh S. hmdb_endogenous_animal (v1.x) [Software]. GitHub; 2025.
