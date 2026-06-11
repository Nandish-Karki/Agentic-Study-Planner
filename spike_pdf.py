"""Phase 1 spike: verify pypdf extracts readable text from each real input.
Run once, eyeball output, then build agents on top. Not part of the package."""
import pathlib
from pypdf import PdfReader

for f in sorted(pathlib.Path("data").glob("*.pdf")):
    reader = PdfReader(str(f))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    print("=" * 70)
    print(f"{f.name}  |  pages: {len(reader.pages)}  |  extracted chars: {len(text)}")
    print("-" * 70)
    print(text[:600].strip() or "!! NO TEXT EXTRACTED — possibly scanned/image PDF !!")
    print()
