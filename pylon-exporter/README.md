# Pylon Exporter 🚀

A lightweight, production-ready toolkit for exporting issues from Pylon and converting it into a Kapa-compatible format.

---

## What the scripts do

- **`pylon_fetcher`** — A resilient data ingestion engine that connects to Pylon, performs efficient, incremental fetches (with retry, pagination, and checkpointing), and stores the raw events in a predictable, auditable format. Designed for scale and operational reliability.

- **`pylon_to_kapa`** — A transformation and enrichment pipeline that turns raw Pylon exports into validated, batched, and schema-compliant Kapa payloads. Includes mapping, lightweight enrichment, and output formatting so downstream consumers can ingest data with confidence.

---

## Quick start

1. Install dependencies: `pip install -r requirements.txt`.
2. Configure credentials and endpoints via environment variables or configuration files.
3. Run `pylon_fetcher` to pull data, then run `pylon_to_kapa` to convert and prepare payloads for ingestion.