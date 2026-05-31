import re


def safe_export_filename(name: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._-")
    stem = re.sub(r"_+", "_", stem)
    stem = stem[:80] or "dataforge_export"
    ext = re.sub(r"[^A-Za-z0-9]+", "", extension or "") or "dat"
    return f"{stem}.{ext}"
