# Thumbnail Blur Pipeline

This is the authoritative specification for how blurred thumbnail variants
work in `dj4xol`.

Use `doc/thumbnail_regeneration.md` for the operational regeneration steps.

## Scope

This document defines:

- why blurred thumbnail variants exist
- what files are generated
- what runtime code is allowed to do
- what production and development environments are expected to contain

It does not define the day-to-day regeneration workflow.

## Problem

Basic-scan reports currently blur thumbnails in the browser with CSS.

That causes two issues:

- the blur softens the visible edge of the image itself
- in framed themes such as `win95`, the softened image edge visually fights the
  frame and makes the thumbnail look like it is bleeding into the border

This is a poor fit for CSS filters. `blur(...)` operates on the rendered image
surface, so clipping the container does not preserve a crisp silhouette.

## Decision

Move basic-report thumbnail blurring into the asset pipeline.

The game should use pre-generated blurred thumbnail variants rather than
runtime CSS blurring.

## Requirements

- support fleet, star, anomaly, and salvage thumbnails
- preserve a crisp alpha edge / silhouette
- keep blurred assets out of the normal thumbnail selection catalogs
- use the blurred asset only for basic-report detail views
- leave advanced, encounter, and owned/current thumbnails unchanged

## Proposed Asset Convention

For every source thumbnail:

- original:
  - `dj4xol/images/thumbs/star/all/1__r01_c01.png`
- blurred variant:
  - `dj4xol/images/thumbs/star/all/1__r01_c01__blur.png`

The `__blur.png` suffix should be treated as a generated variant and excluded
from the normal catalog builders.

## Generation Rules

Use Pillow to generate blurred variants.

- load source as `RGBA`
- blur the colour channels moderately
- preserve the original alpha channel
- optionally apply slight desaturation / dimming so the image reads as
  "uncertain" without becoming muddy

Preserving the original alpha channel is the important part. That keeps the
thumbnail edge sharp even when the interior is softened.

## Runtime Rules

- model thumbnail fields continue storing the canonical original asset path
- the thumbnail-selection modules derive the blurred asset path from the
  original path
- if a blurred asset is missing, fall back to the original asset rather than
  failing
- production should not generate blurred assets
- production should not require Pillow

In other words:

- blur generation is a development-time preprocessing step
- runtime code only resolves already-generated `__blur.png` asset paths
- the modules that own thumbnail access remain responsible for choosing the
  correct asset path

## Catalog Integration

Catalog scripts should:

- generate or refresh blurred variants for the relevant thumbnail tree
- ignore `__blur.png` files when building the normal catalogs

This keeps deterministic thumbnail selection stable and avoids blur variants
being selected as normal object thumbnails.

## Deployment Boundary

`Pillow` is only a development/build dependency for generating blurred assets.

The deployed server should already have:

- original thumbnails
- generated `__blur.png` variants
- generated thumbnail catalog modules

The application server should only read those generated assets and should not
need to perform any image processing.

## Testing

Add coverage for:

- helper mapping original path -> blurred variant path
- fallback to original path when blurred asset is missing
- catalog builders excluding blurred assets
- detail-panel basic report using blurred asset paths

## Related Document

For the actual regeneration commands and verification steps, use
`doc/thumbnail_regeneration.md`.
