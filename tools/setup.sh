#!/usr/bin/env bash
# One-shot setup for the offline building detector.
# Creates a native venv in tools/.venv, installs deps, and verifies OpenCV.
# Run from anywhere:  bash tools/setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "Python : $(python3 --version) ($(command -v python3))"
python3 -c "import platform; print('Arch   :', platform.machine())"
case "$(python3 -c 'import platform;print(platform.machine())')" in
  arm64) : ;;
  *) echo "  (note: not arm64 — native Apple-silicon Python is preferable, but this will still work)";;
esac

if [ ! -d .venv ]; then
  echo "Creating venv in tools/.venv …"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

python - <<'PY'
import cv2, numpy
print(f"OK — OpenCV {cv2.__version__}, NumPy {numpy.__version__}")
PY

mkdir -p outputs

cat <<EOF

Setup complete.

To run the detector:
  cd "$HERE"
  source .venv/bin/activate
  python detect_buildings.py --bbox "7.418,9.030,7.452,9.060" --zoom 18 --out outputs/candidates.geojson

Then in the app:  Projects -> Wuye District -> Import -> Detected footprints (GeoJSON)
(Restart the API first so the endpoint is live:
   docker compose -f infra/docker-compose.yml restart api )
EOF
