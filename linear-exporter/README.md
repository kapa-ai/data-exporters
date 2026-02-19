# Linear Exporter 🚀

A lightweight, production-ready toolkit for exporting issues from Linear and converting them into a Kapa-compatible format.

## What the scripts do

* `linear_fetcher` — A resilient data ingestion engine that connects to the Linear GraphQL API, performs efficient cursor-based pagination across issues and comment threads, and stores the raw data in a predictable, auditable JSON format. Includes workspace diagnostics, configurable state filtering, and team scoping for operational reliability.

* `linear_to_kapa` — A transformation and enrichment pipeline that turns raw Linear exports into validated, Kapa-compliant markdown files with a flat `index.json` manifest for S3 URL mapping. Includes field mapping, timestamp formatting, and output structuring so Kapa can ingest your Linear issues with confidence.

## Quick start

1. Install dependencies: `pip install -r requirements.txt`.
2. Configure your Linear API key via environment variable: `export LINEAR_API_KEY='lin_api_xxxxxxxxxxxx'`.
3. Run `linear_fetcher` to pull data, then run `linear_to_kapa` to convert and prepare files for S3 ingestion into Kapa.
