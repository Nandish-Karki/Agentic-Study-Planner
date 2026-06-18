import pathlib
import re
from crewai.tools import tool
from pypdf import PdfReader

# Per-call character cap — keeps any single tool result within the LLM's
# per-request token budget. GitHub Models free tier allows only 8k tokens for
# the ENTIRE request (system + history + tool results), so each chunk must
# stay small. 5k chars ≈ 1.3k tokens. Longer docs are read in chunks (::2, ::3).
READ_CHAR_CAP = 5_000


def _extract_pdf_text(path: pathlib.Path) -> str:
    """Extract text from every page of a PDF, joined with page markers."""
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages.append(f"--- page {i} ---\n{text}")
    return "\n".join(pages)


def _read_any(path: pathlib.Path) -> str:
    """Read a document: PDF via pypdf, anything else as plain text."""
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


# Input folders tried, by basename, when a bare filename is given (not a full
# path). Both the real run (data/) and the workshop sample run (sample_data/)
# resolve here, so the tools are not hardwired to one directory.
_FALLBACK_DIRS = ("data", "sample_data")


def _resolve_input_path(file_path: str) -> pathlib.Path | None:
    """Resolve a document path. Tries the path exactly as given first (this is
    the normal case — tasks pass the full {data_dir}/... path), then falls back
    to known input folders by basename. Returns None if nothing matches."""
    p = pathlib.Path(file_path.strip())
    if p.exists():
        return p.resolve()
    name = p.name
    for d in _FALLBACK_DIRS:
        candidate = pathlib.Path(d) / name
        if candidate.exists():
            return candidate.resolve()
    return None


@tool("list_input_files")
def list_input_files(directory: str) -> str:
    """
    List the input documents available in a directory (e.g. the data/ folder).
    Returns relative file paths that can be passed directly to read_document.
    Input: a directory path.
    """
    base = pathlib.Path(directory).resolve()
    if not base.exists():
        return f"ERROR: directory not found: {base}"
    files = [f for f in sorted(base.iterdir()) if f.is_file()]
    if not files:
        return f"No files found in {base}"
    lines = [f"Input files in {base}:"]
    for f in files:
        size_kb = f.stat().st_size // 1024
        lines.append(f"  {f.name}  ({size_kb} KB)")
    return "\n".join(lines)


@tool("read_document")
def read_document(file_path: str) -> str:
    """
    Read a document (PDF, .md, or .txt) in chunks of 5000 characters.
    Input: a file path, optionally with a chunk number after '::'.
      "module_handbook.pdf"      → chunk 1 (first 5000 chars)
      "module_handbook.pdf::2"   → chunk 2 (next 5000 chars), and so on
    The output states how many chunks the document has. Read all chunks of a
    document before summarising it.
    """
    chunk_no = 1
    if "::" in file_path:
        file_path, chunk_part = file_path.split("::", 1)
        try:
            chunk_no = max(1, int(chunk_part.strip()))
        except ValueError:
            return f"ERROR: chunk must be a number, got {chunk_part!r}"

    path = _resolve_input_path(file_path)
    if path is None:
        return f"ERROR: file not found: {file_path}. Use list_input_files to see available files."

    try:
        text = _read_any(path)
    except Exception as e:
        return f"ERROR reading {path.name}: {e}"

    # Scanned/image PDF (no embedded text) -> try OCR before giving up.
    if not text.strip() and path.suffix.lower() == ".pdf":
        from study_planner.ingest.ocr import ocr_pdf
        ocr_text = ocr_pdf(path)
        if ocr_text.strip():
            text = ocr_text

    if not text.strip():
        return (
            f"WARNING: {path.name} produced no extractable text — it looks like a "
            "scanned/image PDF and OCR was unavailable. Try uploading a text-based PDF."
        )

    total_chunks = max(1, -(-len(text) // READ_CHAR_CAP))  # ceil division
    if chunk_no > total_chunks:
        return f"ERROR: {path.name} has only {total_chunks} chunk(s)."

    start = (chunk_no - 1) * READ_CHAR_CAP
    body = text[start : start + READ_CHAR_CAP]
    header = f"[{path.name} — chunk {chunk_no}/{total_chunks}]\n"
    footer = (
        f"\n[More content: read '{path.name}::{chunk_no + 1}' for the next chunk.]"
        if chunk_no < total_chunks
        else "\n[End of document.]"
    )
    return header + body + footer


@tool("search_document")
def search_document(query: str) -> str:
    """
    Search for a keyword inside a document and return matching lines with context.
    Essential for large documents like module handbooks that exceed the read limit.
    Input format: "keyword::path"  — pass the SAME file path you would give to
    read_document (the full path from the task is safest), e.g.
    "Machine Learning::data/module_handbook.pdf". A bare filename also works and
    is resolved against the known input folders. Returns up to 20 matches with
    2 lines of context around each.
    """
    if "::" not in query:
        return "ERROR: input must be 'keyword::path', e.g. 'Data Mining::data/module_handbook.pdf'"
    keyword, filename = query.split("::", 1)
    keyword = keyword.strip()

    path = _resolve_input_path(filename)
    if path is None:
        return f"ERROR: file not found: {filename}. Use list_input_files to see available files."

    try:
        text = _read_any(path)
    except Exception as e:
        return f"ERROR reading {path.name}: {e}"

    lines = text.splitlines()
    matches = []
    for i, line in enumerate(lines):
        if keyword.lower() in line.lower():
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            chunk = "\n".join(lines[start:end])
            matches.append(f"[line {i+1}]\n{chunk}")
            if len(matches) >= 20:
                break

    if not matches:
        return f"No matches for '{keyword}' in {path.name}"
    return f"Matches for '{keyword}' in {path.name}:\n\n" + "\n\n".join(matches)


# ── Input-extraction diagnosis (debug/observability) ───────────────────────────
# Core documents the crew expects; reported as MISSING if absent.
_EXPECTED_INPUTS = ("cv.pdf", "transcript.pdf", "career.pdf", "module_handbook.pdf")

# Below this many extracted chars per page a PDF is almost certainly scanned /
# image-only — pypdf gets nothing usable and every downstream agent hallucinates.
# No RAG fixes this; it needs OCR. Surfacing it is the cheapest, highest-value check.
_UNREADABLE_CHARS_PER_PAGE = 100


def diagnose_inputs(data_dir) -> list[dict]:
    """Report text-extraction health for every PDF in ``data_dir``.

    Returns one row per PDF (plus a row for any missing expected input) with the
    page count, total extracted characters, chars-per-page, and a
    ``looks_unreadable`` flag. This is the cheapest check for the highest-impact
    hidden failure mode: a scanned CV/transcript that yields near-empty text
    poisons the whole pipeline and cannot be fixed by retrieval — only OCR.
    """
    base = pathlib.Path(data_dir)
    rows: list[dict] = []
    seen: set[str] = set()
    pdfs = sorted(base.glob("*.pdf")) if base.exists() else []
    for path in pdfs:
        seen.add(path.name)
        row = {"file": path.name, "size_kb": path.stat().st_size // 1024}
        try:
            reader = PdfReader(str(path))
            pages = len(reader.pages)
            # Strip the synthetic page markers so the char count is honest.
            text = re.sub(r"--- page \d+ ---", "", _extract_pdf_text(path)).strip()
            chars = len(text)
            per_page = chars // pages if pages else 0
            row.update(pages=pages, chars=chars, chars_per_page=per_page,
                       looks_unreadable=(pages > 0 and per_page < _UNREADABLE_CHARS_PER_PAGE))
        except Exception as e:
            row.update(pages=0, chars=0, chars_per_page=0,
                       looks_unreadable=True, error=str(e))
        rows.append(row)
    for name in _EXPECTED_INPUTS:
        if name not in seen:
            rows.append({"file": name, "missing": True})
    return rows


def format_input_diagnosis(rows: list[dict]) -> str:
    """Render :func:`diagnose_inputs` output as a Markdown report."""
    lines = ["# Input extraction diagnosis", "",
             "| File | Size KB | Pages | Chars | Chars/page | Status |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("missing"):
            lines.append(f"| {r['file']} | - | - | - | - | MISSING |")
            continue
        if r.get("error"):
            status = f"ERROR: {r['error']}"
        elif r.get("looks_unreadable"):
            status = "LIKELY SCANNED / NEEDS OCR"
        else:
            status = "ok"
        lines.append(
            f"| {r['file']} | {r.get('size_kb', '')} | {r.get('pages', '')} | "
            f"{r.get('chars', '')} | {r.get('chars_per_page', '')} | {status} |")
    lines += ["",
              "_Files flagged LIKELY SCANNED extract almost no text; retrieval "
              "(RAG) cannot fix this -- they need OCR. Fix these first._"]
    return "\n".join(lines)
