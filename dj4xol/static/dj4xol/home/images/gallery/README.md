# Gallery Images

This directory is for local screenshot assets used by the landing/gallery pages.

## Notes

- Image files in this directory are intentionally ignored by git.
- Keep only placeholder/meta files (`.gitkeep`, `.gitignore`, `README.md`) in version control.

## Converting PNG screenshots to JPEG

Use the local helper script:

```bash
python local_scripts/convert_gallery_pngs.py
```

Useful options:

```bash
python local_scripts/convert_gallery_pngs.py --quality 90 --overwrite
python local_scripts/convert_gallery_pngs.py --delete-source
python local_scripts/convert_gallery_pngs.py --dry-run
```
