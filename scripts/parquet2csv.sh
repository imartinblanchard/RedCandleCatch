#!/usr/bin/env bash
# Convertit un .parquet en .csv (ouvrable dans Excel/LibreOffice).
# Usage : ./scripts/parquet2csv.sh data/collected/bars/2026-09-18.parquet
set -euo pipefail
cd "$(dirname "$0")/.."
IN="$1"
OUT="${IN%.parquet}.csv"
.venv/bin/python3 -c "import pandas as pd; pd.read_parquet('$IN').to_csv('$OUT', index=False)"
echo "✅ $OUT"
