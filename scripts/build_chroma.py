#!/usr/bin/env python
"""Build the ChromaDB collection from ``document/``.

Standalone CLI port of ``01_embed_documents_chroma.ipynb``. It loads every
supported document under ``document/``, chunks the text, and embeds the chunks
into a persistent ChromaDB collection (idempotent: only new chunks are added).

Embedding backend selection mirrors the notebook / ``manufacturing_agent.rag``:
  - If ``OPENAI_API_KEY`` is set (and OpenAI embeddings are not disabled),
    OpenAI ``text-embedding-3-small`` is used -> collection
    ``manufacturing_document_chunks_openai``.
  - Otherwise a deterministic local hash embedding is used -> collection
    ``manufacturing_document_chunks_local_hash`` (no network / no quota).

Usage:
    python scripts/build_chroma.py                # incremental build
    python scripts/build_chroma.py --reset        # drop + rebuild collection
    python scripts/build_chroma.py --dry-run      # report plan, do not embed

NOTE: With OPENAI_API_KEY set, embedding calls the OpenAI API and consumes
quota. Use the local-hash backend (no key, or --local) for offline builds.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils import embedding_functions

# --- paths / config (kept identical to the notebook) -------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = str(PROJECT_ROOT / "agent_data")
DOCUMENT_DIR = str(PROJECT_ROOT / "document")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
EMBED_MODEL = "text-embedding-3-small"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
LOCAL_EMBED_DIM = 384
BATCH_SIZE = 64


def load_dotenv(path: str | None = None) -> None:
    """Minimal .env loader (does not overwrite existing env vars)."""
    env_path = Path(path) if path else (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# --- embedding backend -------------------------------------------------------
class LocalHashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic local embedding (no external model download / no API)."""

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for text in input:
            vec = [0.0] * LOCAL_EMBED_DIM
            tokens = re.findall(r"[A-Za-z가-힣0-9_]+", text.lower())
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "little") % LOCAL_EMBED_DIM
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def build_embedding_function(use_openai: bool):
    """Return (embedding_function, collection_name, label).

    Must stay consistent with 01_embed_documents_chroma.ipynb and
    manufacturing_agent/rag/chroma.py so the runtime can read what we write.
    """
    model = os.environ.get("OPENAI_EMBED_MODEL", EMBED_MODEL)
    if use_openai:
        return (
            embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.environ["OPENAI_API_KEY"], model_name=model
            ),
            "manufacturing_document_chunks_openai",
            f"OpenAI({model})",
        )
    return (
        LocalHashEmbeddingFunction(),
        "manufacturing_document_chunks_local_hash",
        f"LocalHash({LOCAL_EMBED_DIM})",
    )


# --- document loading / chunking --------------------------------------------
def doc_type(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "osha" in parts or "kosha" in parts or "safety" in name or "loto" in name or "guard" in name:
        return "safety"
    if "haas" in parts or "troubleshooting" in name or "diagnostic" in name:
        return "troubleshooting"
    return "concept"


def read_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    return soup.get_text("\n")


def read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "PDF embedding requires pypdf. Install it (uv add pypdf) and retry."
        ) from e
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def clean_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if len(line) >= 2)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def load_document_chunks(document_dir: str = DOCUMENT_DIR) -> list[dict]:
    root = Path(document_dir)
    supported = sorted(
        p for p in root.rglob("*")
        if p.suffix.lower() in {".html", ".htm", ".pdf", ".txt", ".md"}
    )
    chunks: list[dict] = []
    for path in supported:
        suffix = path.suffix.lower()
        if suffix in {".html", ".htm"}:
            text = read_html(path)
        elif suffix == ".pdf":
            text = read_pdf(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")

        rel = path.relative_to(root).as_posix()
        for idx, chunk in enumerate(chunk_text(text)):
            digest = hashlib.sha1(f"{rel}:{idx}:{chunk[:80]}".encode("utf-8")).hexdigest()[:16]
            chunks.append({
                "id": digest,
                "text": chunk,
                "metadata": {
                    "source": rel,
                    "chunk_index": idx,
                    "type": doc_type(path),
                    "ext": suffix.lstrip("."),
                },
            })
    return chunks


# --- chroma collection -------------------------------------------------------
def get_collection(embed_fn, collection_name: str, reset: bool = False):
    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
    # cosine space so runtime score = 1.0 - distance is a 0..1 similarity.
    return client.get_or_create_collection(
        collection_name,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def embed_documents_to_chroma(collection, new_chunks: list[dict]) -> None:
    for i in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[i:i + BATCH_SIZE]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ChromaDB collection from document/.")
    parser.add_argument("--reset", action="store_true", help="Drop and rebuild the collection.")
    parser.add_argument("--dry-run", action="store_true", help="Report the plan, do not embed.")
    parser.add_argument("--local", action="store_true",
                        help="Force the local-hash backend even if OPENAI_API_KEY is set.")
    args = parser.parse_args()

    load_dotenv()
    use_openai = bool(os.environ.get("OPENAI_API_KEY")) and not args.local

    embed_fn, collection_name, embed_label = build_embedding_function(use_openai)
    print("ChromaDB path:", CHROMA_DIR)
    print("Document path:", DOCUMENT_DIR)
    print("Collection:", collection_name)
    print("Embedding:", embed_label)

    chunks = load_document_chunks()
    print("Loaded chunks:", len(chunks))
    if not chunks:
        print("No documents found under", DOCUMENT_DIR, "- nothing to embed.")
        return 1

    collection = get_collection(embed_fn, collection_name, reset=args.reset)
    existing_ids = set(collection.get(include=[])["ids"]) if collection.count() else set()
    target_ids = {c["id"] for c in chunks}
    new_chunks = [c for c in chunks if c["id"] not in existing_ids]
    stale_ids = existing_ids - target_ids

    print("stored_chunks:", collection.count())
    print("document_chunks:", len(chunks))
    print("new_chunks:", len(new_chunks))
    print("stale_chunks:", len(stale_ids))
    if stale_ids:
        print("NOTE: chunks exist in ChromaDB that are no longer in document/. "
              "Use --reset to fully rebuild if needed.")

    if args.dry_run:
        print("Dry run - no embedding performed.")
        return 0

    if not new_chunks:
        print("Collection already up to date. Nothing to embed.")
        return 0

    embed_documents_to_chroma(collection, new_chunks)
    print("ChromaDB embedding complete.")
    print("collection:", collection_name)
    print("embedding:", embed_label)
    print("total:", collection.count())
    print("added:", len(new_chunks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
