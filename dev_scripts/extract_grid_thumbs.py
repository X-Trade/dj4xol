#!/usr/bin/env python3
"""Extract individual tiles from a grid image.

Defaults to a 3x2 grid (3 across, 2 down). You can override with
--grid-width and --grid-height.
"""

from __future__ import print_function

import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract thumbnails from a grid image."
    )
    parser.add_argument("input_image", help="Path to source image")
    parser.add_argument(
        "--grid-width",
        type=int,
        default=3,
        help="Number of columns in the grid (default: 3)",
    )
    parser.add_argument(
        "--grid-height",
        type=int,
        default=2,
        help="Number of rows in the grid (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <input_stem>_thumbs)",
    )
    parser.add_argument(
        "--prefix",
        default="thumb",
        help="Filename prefix for output files (default: thumb)",
    )
    parser.add_argument(
        "--trim-left",
        type=int,
        default=0,
        help="Pixels to trim from each tile's left edge after extraction",
    )
    parser.add_argument(
        "--trim-top",
        type=int,
        default=0,
        help="Pixels to trim from each tile's top edge after extraction",
    )
    parser.add_argument(
        "--trim-right",
        type=int,
        default=0,
        help="Pixels to trim from each tile's right edge after extraction",
    )
    parser.add_argument(
        "--trim-bottom",
        type=int,
        default=0,
        help="Pixels to trim from each tile's bottom edge after extraction",
    )
    return parser.parse_args()


def build_output_dir(input_image, output_dir):
    if output_dir:
        return output_dir
    stem = os.path.splitext(os.path.basename(input_image))[0]
    parent = os.path.dirname(os.path.abspath(input_image))
    return os.path.join(parent, stem + "_thumbs")


def grid_bounds(size, steps):
    """Return step boundary indices that span full size."""
    # This preserves the full image even if size is not evenly divisible.
    return [int(round(i * size / float(steps))) for i in range(steps + 1)]


def extract_tiles(
    input_image, grid_width, grid_height, output_dir, prefix,
    trim_left=0, trim_top=0, trim_right=0, trim_bottom=0,
):
    image = Image.open(input_image)
    width, height = image.size

    x_edges = grid_bounds(width, grid_width)
    y_edges = grid_bounds(height, grid_height)

    root_ext = os.path.splitext(input_image)[1].lower()
    ext = root_ext if root_ext else ".png"

    count = 0
    for row in range(grid_height):
        for col in range(grid_width):
            left = x_edges[col]
            right = x_edges[col + 1]
            top = y_edges[row]
            bottom = y_edges[row + 1]
            tile = image.crop((left, top, right, bottom))
            trimmed_right = tile.width - trim_right
            trimmed_bottom = tile.height - trim_bottom
            if (
                trim_left < 0 or trim_top < 0 or trim_right < 0 or trim_bottom < 0 or
                trim_left >= trimmed_right or trim_top >= trimmed_bottom
            ):
                raise ValueError(
                    "Invalid trim values for tile size {}x{}".format(
                        tile.width, tile.height
                    )
                )
            if trim_left or trim_top or trim_right or trim_bottom:
                tile = tile.crop((trim_left, trim_top, trimmed_right, trimmed_bottom))

            filename = "{prefix}_r{row:02d}_c{col:02d}{ext}".format(
                prefix=prefix,
                row=row + 1,
                col=col + 1,
                ext=ext,
            )
            out_path = os.path.join(output_dir, filename)
            tile.save(out_path)
            count += 1

    return count


def main():
    args = parse_args()

    if args.grid_width < 1 or args.grid_height < 1:
        print("Error: --grid-width and --grid-height must be >= 1")
        return 2
    for trim_value in (
        args.trim_left, args.trim_top, args.trim_right, args.trim_bottom
    ):
        if trim_value < 0:
            print("Error: trim values must be >= 0")
            return 2

    if not os.path.isfile(args.input_image):
        print("Error: input image not found: {}".format(args.input_image))
        return 2

    output_dir = build_output_dir(args.input_image, args.output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    count = extract_tiles(
        input_image=args.input_image,
        grid_width=args.grid_width,
        grid_height=args.grid_height,
        output_dir=output_dir,
        prefix=args.prefix,
        trim_left=args.trim_left,
        trim_top=args.trim_top,
        trim_right=args.trim_right,
        trim_bottom=args.trim_bottom,
    )

    print(
        "Wrote {} tiles to {}".format(
            count,
            output_dir,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
