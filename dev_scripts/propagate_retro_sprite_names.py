#!/usr/bin/env python3
"""Propagate curated retro fleet sprite names across palette folders.

Workflow:
1. Rename one or more files in the reference folder (typically `friendly/`)
   from the extracted grid names like `friendly_r01_c01.png` to semantic names
   like `fighter.png`, `frigate.png`, etc.
2. Run this script in dry-run mode to see which files in the target folders
   (`allied/`, `enemy/`) match by normalized sprite signature.
3. Re-run with `--apply` to perform the renames.

Matching is palette-independent: it hashes a normalized grayscale/high-contrast
version of each sprite, so files that only differ by palette should still map
to the same semantic name.
"""

from __future__ import print_function

import argparse
import hashlib
import os
import re
import sys

from PIL import Image, ImageEnhance, ImageOps


GRID_NAME_RE = re.compile(r"^(friendly|allied|enemy)(?:_\d+)?_r\d{2}_c\d{2}$", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Propagate curated retro sprite names to sibling palette folders."
    )
    parser.add_argument(
        "--reference-dir",
        default="dj4xol/static/dj4xol/images/mapfleet/retro/source/friendly",
        help="Folder containing curated canonical filenames",
    )
    parser.add_argument(
        "--target-dir",
        action="append",
        dest="target_dirs",
        default=[],
        help="Target folder to rename by signature (can be repeated)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files instead of just printing the plan",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra diagnostics",
    )
    return parser.parse_args()


def is_grid_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return bool(GRID_NAME_RE.match(stem))


def natural_sort_key(text):
    parts = re.split(r"(\d+)", str(text or ""))
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


def list_pngs(folder):
    if not os.path.isdir(folder):
        raise ValueError("Folder not found: %s" % folder)
    paths = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".png"):
            continue
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            paths.append(full)
    return paths


def normalize_sprite(path):
    """Normalize a sprite to a palette-independent grayscale signature."""
    img = Image.open(path).convert("RGBA")
    alpha = img.getchannel("A")
    # Palette differences should collapse under grayscale + strong normalization.
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Brightness(gray).enhance(1.35)
    gray = ImageEnhance.Contrast(gray).enhance(2.4)
    # Use alpha as a shape gate so transparent background noise does not matter.
    normalized = Image.new("L", img.size, 0)
    normalized.paste(gray, mask=alpha)
    # Reduce remaining palette variance into a stable binary-ish mask.
    normalized = normalized.point(lambda value: 255 if value >= 24 else 0)
    return normalized


def sprite_signature(path):
    normalized = normalize_sprite(path)
    payload = b"%dx%d|" % normalized.size + normalized.tobytes()
    return hashlib.sha1(payload).hexdigest()


def build_reference_name_map(reference_dir, verbose=False):
    reference_map = {}
    for path in list_pngs(reference_dir):
        if is_grid_name(path):
            continue
        signature = sprite_signature(path)
        name = os.path.basename(path)
        reference_map.setdefault(signature, []).append(name)
        if verbose:
            print("REF %s -> %s" % (name, signature))
    if not reference_map:
        raise ValueError(
            "No curated reference files found in %s. Rename one or more files "
            "away from the extracted grid names first." % reference_dir
        )
    for signature in reference_map:
        reference_map[signature] = sorted(
            reference_map[signature],
            key=natural_sort_key,
        )
    return reference_map


def planned_target_renames(target_dir, reference_map, verbose=False):
    plans = []
    warnings = []
    target_paths = list_pngs(target_dir)
    by_signature = {}
    for path in target_paths:
        signature = sprite_signature(path)
        by_signature.setdefault(signature, []).append(path)

    for signature, desired_names in sorted(reference_map.items()):
        current_paths = sorted(by_signature.get(signature, []), key=natural_sort_key)
        if not current_paths:
            continue
        desired_names = list(desired_names)
        reserved = set()

        for path in list(current_paths):
            current_name = os.path.basename(path)
            if current_name in desired_names:
                reserved.add(current_name)
                current_paths.remove(path)
                if verbose:
                    print("OK  %s already matches" % path)

        remaining_names = [
            name for name in desired_names
            if name not in reserved
        ]
        if not remaining_names:
            continue

        current_paths = sorted(current_paths, key=natural_sort_key)
        remaining_names = sorted(remaining_names, key=natural_sort_key)
        if len(current_paths) < len(remaining_names):
            missing = remaining_names[len(current_paths):]
            warnings.append(
                "Skipping unmatched names in %s: %s" % (
                    target_dir,
                    ", ".join(missing),
                )
            )
            remaining_names = remaining_names[:len(current_paths)]
        for path, desired_name in zip(current_paths, remaining_names):
            current_name = os.path.basename(path)
            if current_name == desired_name:
                continue
            destination = os.path.join(target_dir, desired_name)
            plans.append((path, destination))
    return plans, warnings


def apply_renames(plans):
    for source, destination in plans:
        if os.path.exists(destination):
            raise ValueError(
                "Destination already exists: %s (from %s)" % (destination, source)
            )
    for source, destination in plans:
        os.rename(source, destination)


def main():
    args = parse_args()
    target_dirs = args.target_dirs or [
        "dj4xol/static/dj4xol/images/mapfleet/retro/source/allied",
        "dj4xol/static/dj4xol/images/mapfleet/retro/source/enemy",
    ]

    try:
        reference_map = build_reference_name_map(
            args.reference_dir,
            verbose=args.verbose,
        )
        all_plans = []
        all_warnings = []
        for target_dir in target_dirs:
            plans, warnings = planned_target_renames(
                target_dir,
                reference_map,
                verbose=args.verbose,
            )
            all_plans.extend(plans)
            all_warnings.extend(warnings)
            if plans:
                print("[%s]" % target_dir)
                for source, destination in plans:
                    print("  %s -> %s" % (
                        os.path.basename(source),
                        os.path.basename(destination),
                    ))
            else:
                print("[%s]" % target_dir)
                print("  no matching renames")
        for warning in all_warnings:
            print("WARN %s" % warning)
        if not args.apply:
            print("Dry run only. Re-run with --apply to rename files.")
            return 0
        apply_renames(all_plans)
        print("Applied %d renames." % len(all_plans))
        return 0
    except Exception as exc:
        print("Error: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
