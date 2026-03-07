# Thumbnail Regeneration

## Purpose

Use this when thumbnail source images change, when the blur recipe changes, or
when the generated thumbnail catalogs need refreshing.

This is a development/build-side process.

The production server is expected to serve pre-generated thumbnail assets and
should not require `Pillow`.

## One-Step Regeneration

From the project root:

```sh
pyenv exec python -m dj4xol.catalog_all_thumbs
```

This will:

- regenerate all `__blur.png` thumbnail variants
- refresh the generated star thumbnail catalog
- refresh the generated ship thumbnail catalog
- refresh the generated anomaly thumbnail catalog

The bulk script currently forces a full refresh of blur assets so recipe changes
are applied immediately.

After running it, the generated assets and catalog modules should be included in
the deployed code/static tree.

## Individual Catalog Scripts

If needed, these can also be run directly:

```sh
pyenv exec python -m dj4xol.catalog_star_thumbs
pyenv exec python -m dj4xol.catalog_ship_thumbs
pyenv exec python -m dj4xol.catalog_anomaly_thumbs
```

## Notes

- blurred variants use the `__blur.png` suffix
- blur variants are generated assets and are excluded from the normal thumbnail
  selection catalogs
- runtime code only resolves pre-generated variant paths; it does not generate
  new images
- salvage thumbnails do not have a generated Python catalog module, but their
  blurred variants are refreshed by `dj4xol.catalog_all_thumbs`

## Verification

After regeneration, a useful targeted test pass is:

```sh
pyenv exec python manage.py test dj4xol.tests.thumbnails dj4xol.tests.views
```
