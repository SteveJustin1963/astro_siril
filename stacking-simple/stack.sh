#!/usr/bin/env bash
# Astronomy image stacker for iPhone photos
# Usage: ./stack.sh
# Drop your photos (JPEG, HEIC, DNG, TIFF, PNG) into input/ then run this script.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT="$SCRIPT_DIR/input"
PROCESS="$SCRIPT_DIR/process"
OUTPUT="$SCRIPT_DIR/output"
SSF="$SCRIPT_DIR/stack.ssf"

mkdir -p "$INPUT" "$PROCESS" "$OUTPUT"

# ── Find all supported image files ──────────────────────────────────────────
mapfile -t FILES < <(find "$INPUT" -maxdepth 1 -type f \
    \( -iname "*.jpg" -o -iname "*.jpeg" \
       -o -iname "*.heic" -o -iname "*.heif" \
       -o -iname "*.tif"  -o -iname "*.tiff" \
       -o -iname "*.png"  -o -iname "*.dng" \
       -o -iname "*.fit"  -o -iname "*.fits" \) | sort)

COUNT=${#FILES[@]}

if [ "$COUNT" -eq 0 ]; then
    echo "No images found in input/"
    echo "Put your iPhone photos in input/ (JPEG, HEIC, DNG, TIFF, PNG) and run again."
    exit 0
fi

echo "Found $COUNT image(s) in input/"
echo ""

# ── Clean previous process files ─────────────────────────────────────────────
rm -f "$PROCESS"/*.fit 2>/dev/null || true

# ── Pick stacking method based on frame count ────────────────────────────────
# Rejection needs ~7+ frames to work reliably; below that use mean or sum.
if [ "$COUNT" -ge 7 ]; then
    STACK_METHOD="rej 3 3"
    echo "Stack method: sigma-rejection (best quality, needs 7+ frames)"
elif [ "$COUNT" -ge 3 ]; then
    STACK_METHOD="mean"
    echo "Stack method: mean (add more frames for better noise reduction)"
else
    STACK_METHOD="sum"
    echo "Stack method: sum ($COUNT frame(s) — stack more for best results)"
fi

# ── Generate Siril script ────────────────────────────────────────────────────
cat > "$SSF" <<SSF
requires 1.3.0

# Convert source images to Siril FITS format
cd $INPUT
convert light -out=$PROCESS

# Register (star-align) all frames
cd $PROCESS
register light

# Stack into a single 32-bit result
stack r_light $STACK_METHOD -norm=addscale -output_norm -rgb_equal -32b -out=$OUTPUT/stacked

# Flip to display orientation and auto-stretch for a viewable preview
load $OUTPUT/stacked
mirrorx -bottomup
autostretch
savetif $OUTPUT/preview
savejpg $OUTPUT/preview 95

close
SSF

# ── Run Siril ────────────────────────────────────────────────────────────────
echo "Trying Siril star-alignment… (best for wide star fields)"
echo "──────────────────────────────────────────────────────────"
siril -s "$SSF" 2>&1 | grep -Ev "^\s*$|^\[" | sed 's/^/  /'
echo "──────────────────────────────────────────────────────────"
echo ""

# ── If Siril succeeded, report and exit ──────────────────────────────────────
if [ -f "$OUTPUT/stacked.fit" ]; then
    echo "Done! Results in output/"
    echo ""
    echo "  preview.jpg   ← open this for a quick look"
    echo "  preview.tif   ← for editing in Lightroom / GIMP"
    echo "  stacked.fit   ← full 32-bit FITS (open in Siril for more processing)"
    echo ""
    ls -lh "$OUTPUT/"
    exit 0
fi

# ── Siril couldn't align — fall back to centroid (planet/single-star) mode ───
echo "Siril couldn't find enough stars to align frames."
echo "Switching to planet/single-object mode (centroid alignment)…"
echo ""
python3 "$SCRIPT_DIR/stack_planet.py" "$INPUT" "$OUTPUT"

if [ -f "$OUTPUT/preview.jpg" ]; then
    echo ""
    echo "Done! Results in output/"
    echo ""
    echo "  preview.jpg   ← open this for a quick look"
    echo "  preview.tif   ← for editing in Lightroom / GIMP"
    echo ""
    ls -lh "$OUTPUT/"
else
    echo "Stacking failed. Check the output above for errors."
fi
