#!/bin/sh
# Loads one real breast MRI (Duke Breast_MRI_001 from the NCI Imaging Data Commons) into the local Orthanc,
# so the viewer can be tried on real images. The data is CC BY-NC 4.0, stays in data/duke (git-ignored)
# and only ever goes to the Orthanc on this machine. Needs uv and the stack running (docker compose up).
set -e

cd "$(dirname "$0")/../.."
PATIENT="${1:-Breast_MRI_001}"
ORTHANC="${ORTHANC_LOCAL_URL:-http://localhost:8042}"
LOGIN="$(grep '^ORTHANC_USER=' .env 2>/dev/null | cut -d= -f2)"
PASSWORD="$(grep '^ORTHANC_PASSWORD=' .env 2>/dev/null | cut -d= -f2)"

uv run --no-project --with idc-index python - "$PATIENT" <<'EOF'
import sys
from idc_index import IDCClient

client = IDCClient.client()
series = client.sql_query(
    "SELECT SeriesInstanceUID, SeriesDescription, series_size_MB FROM index "
    f"WHERE collection_id = 'duke_breast_cancer_mri' AND PatientID = '{sys.argv[1]}'"
)
print(series.to_string(index=False))
client.download_dicom_series(seriesInstanceUID=series["SeriesInstanceUID"].tolist(), downloadDir="data/duke")
EOF

ok=0
failed=0
for file in $(find data/duke -type f -name "*.dcm"); do
    code=$(curl -s -o /dev/null -w "%{http_code}" -u "${LOGIN:-orthanc}:${PASSWORD:-orthanc}" -X POST "$ORTHANC/instances" --data-binary "@$file")
    if [ "$code" = 200 ]; then ok=$((ok + 1)); else failed=$((failed + 1)); fi
done
echo "uploaded $ok, failed $failed"
