"""Create a source-only distribution of the invoice review application.

The archive intentionally excludes OCR model weights, SQLite databases,
uploaded invoice/certificate images, caches, and generated outputs.
"""
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "invoice-review-program.tar.gz"
OUT.parent.mkdir(exist_ok=True)

EXCLUDED_PARTS = {
    "data", "images", "models", "paddle_models", "__pycache__",
    "launch_check", "validation", "outputs", ".git", ".venv",
}
INCLUDE_SUFFIXES = {
    ".py", ".html", ".js", ".css", ".txt", ".md", ".service", ".conf",
    ".json", ".cmd", ".ps1",
}

with tarfile.open(OUT, "w:gz") as archive:
    for top in ("cert_demo", "invoice_demo", "ocr_benchmark", "deploy", "docs"):
        folder = ROOT / top
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in INCLUDE_SUFFIXES:
                continue
            archive.add(path, arcname=str(rel).replace("\\", "/"))
    manifest = """Invoice review program source distribution\n\nIncluded: application code, browser assets, deployment templates, tests and documentation.\nExcluded: OCR model weights, SQLite databases, uploaded images/PDFs, caches and generated outputs.\n\nInstall the versions in cert_demo/requirements.txt and deploy/requirements-cpu.txt.\nSet CERT_OCR_MODEL_ROOT to a separately provisioned model directory before starting OCR.\n"""
    import io
    info = tarfile.TarInfo("PROGRAM_PACKAGE.txt")
    encoded = manifest.encode("utf-8")
    info.size = len(encoded)
    archive.addfile(info, io.BytesIO(encoded))

print(f"created={OUT}")
print(f"bytes={OUT.stat().st_size}")
