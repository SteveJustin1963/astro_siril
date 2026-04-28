#!/usr/bin/env python3
"""
Lucky-imaging stacker for single-object astrophotos (planets, bright stars, Moon).
Aligns frames on the brightest object's centroid, scores by sharpness, then stacks.
"""

import sys, os, glob
import numpy as np
from PIL import Image
from scipy import ndimage

EXTS = ('jpg', 'jpeg', 'heic', 'heif', 'tif', 'tiff', 'png', 'dng')


def load_image(path):
    return np.array(Image.open(path).convert('RGB'), dtype=np.float32)


def find_object_center(arr):
    """Peak of a Gaussian-smoothed image — robust for a single point source."""
    gray = arr.mean(axis=2)
    blurred = ndimage.gaussian_filter(gray, sigma=15)
    cy, cx = np.unravel_index(np.argmax(blurred), blurred.shape)
    return float(cy), float(cx)


def sharpness_score(arr):
    """Laplacian variance — higher means sharper."""
    gray = ndimage.uniform_filter(arr.mean(axis=2), size=3)
    return float(ndimage.laplace(gray).var())


def autostretch(arr):
    """Per-channel percentile stretch → uint8."""
    out = np.empty_like(arr)
    for c in range(3):
        ch = arr[:, :, c]
        lo, hi = np.percentile(ch, 0.5), np.percentile(ch, 99.5)
        out[:, :, c] = np.clip((ch - lo) / max(hi - lo, 1e-6), 0, 1)
    return (out * 255).astype(np.uint8)


def main(input_dir, output_dir, keep_pct=80):
    files = []
    for ext in EXTS:
        files += glob.glob(os.path.join(input_dir, f'*.{ext}'))
        files += glob.glob(os.path.join(input_dir, f'*.{ext.upper()}'))
    files = sorted(set(files))

    if not files:
        print(f"No images found in {input_dir}/")
        return False

    print(f"Loading {len(files)} image(s)...")
    frames = []
    for f in files:
        try:
            frames.append((f, load_image(f)))
        except Exception as e:
            print(f"  Warning: skipping {os.path.basename(f)}: {e}")

    if len(frames) == 1:
        print("Single frame — skipping stacking, just stretching.")
        _, arr = frames[0]
        os.makedirs(output_dir, exist_ok=True)
        Image.fromarray(autostretch(arr)).save(
            os.path.join(output_dir, 'preview.jpg'), quality=95)
        Image.fromarray(autostretch(arr)).save(
            os.path.join(output_dir, 'preview.tif'))
        return True

    # Score by sharpness and keep the best fraction
    print("Scoring frames by sharpness...")
    scored = sorted(
        [(sharpness_score(arr), path, arr) for path, arr in frames],
        reverse=True
    )
    keep_n = max(2, round(len(scored) * keep_pct / 100))
    best = scored[:keep_n]
    print(f"  Keeping {keep_n}/{len(scored)} sharpest frames  "
          f"(scores {best[0][0]:.0f}–{best[-1][0]:.0f})")

    # Reference frame = sharpest
    _, ref_path, ref_arr = best[0]
    ref_cy, ref_cx = find_object_center(ref_arr)
    print(f"  Reference: {os.path.basename(ref_path)}")
    print(f"  Object at ({ref_cx:.1f}, {ref_cy:.1f}) px")

    # Align and stack
    print(f"\nAligning and stacking {keep_n} frames...")
    accumulator = np.zeros_like(ref_arr, dtype=np.float64)
    for i, (score, path, arr) in enumerate(best):
        cy, cx = find_object_center(arr)
        dy, dx = ref_cy - cy, ref_cx - cx
        shifted = np.stack([
            ndimage.shift(arr[:, :, c], (dy, dx), order=3, mode='reflect')
            for c in range(3)
        ], axis=2)
        accumulator += shifted
        print(f"  [{i+1:3d}/{keep_n}] shift=({dy:+.1f}, {dx:+.1f})px  "
              f"sharpness={score:.0f}  {os.path.basename(path)}")

    stacked = (accumulator / keep_n).astype(np.float32)

    os.makedirs(output_dir, exist_ok=True)
    preview = autostretch(stacked)
    Image.fromarray(preview).save(
        os.path.join(output_dir, 'preview.jpg'), quality=95)
    Image.fromarray(preview).save(
        os.path.join(output_dir, 'preview.tif'))
    return True


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    inp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(script_dir, 'input')
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(script_dir, 'output')
    ok = main(inp, out)
    sys.exit(0 if ok else 1)
