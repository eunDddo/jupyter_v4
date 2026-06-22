# Running the Manufacturing Agent

All Python commands run through `uv`. Install deps once:

```bash
uv sync --all-extras
```

## 1. Build the ChromaDB index

The RAG layer reads a persisted ChromaDB collection built from `document/`.
Build it before running live chat:

```bash
python scripts/build_chroma.py            # incremental
python scripts/build_chroma.py --reset    # full rebuild
python scripts/build_chroma.py --local    # local-hash embeddings, no API/quota
python scripts/build_chroma.py --dry-run  # report plan only
```

- With `OPENAI_API_KEY` set, this embeds via OpenAI `text-embedding-3-small`
  (collection `manufacturing_document_chunks_openai`) and **consumes quota**.
- Without a key (or with `--local`), it uses a deterministic local-hash backend
  (collection `manufacturing_document_chunks_local_hash`) — offline, no cost.

## 2. Configure `.env`

Create `.env` in the project root (see `.env copy.example`):

```env
OPENAI_API_KEY=sk-...
# optional:
# OPENAI_EMBED_MODEL=text-embedding-3-small
```

The API auto-loads `.env`. A valid key is required for live chat (the LLM
planner / agents). Without it, `/chat` returns `503 llm_quota_exhausted` or a
guardrail-blocked response.

## 3. Run the API

```bash
uvicorn api.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs · Health: `GET /healthz`, `GET /readyz`

## 4. Test flow

```bash
# (a) create a user -> returns {"user_id": "...", ...}
curl -s -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" -d '{}'

# (b) create a thread for that user -> returns {"thread_id": "...", ...}
curl -s -X POST http://127.0.0.1:8000/users/<USER_ID>/threads \
  -H "Content-Type: application/json" -d '{}'

# (c) chat (user_id + thread_id + message in the body)
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<USER_ID>","thread_id":"<THREAD_ID>","message":"설비 고장 원인을 알려줘"}'
```

`POST /chat` accepts optional `input_features` (structured machine readings) and
a `?debug=true` query flag that adds gate/task trace info to the response.

> **Quota note:** live `/chat` calls the OpenAI LLM. If quota is exhausted the
> endpoint returns `503 llm_quota_exhausted`. Build chroma with `--local` and
> run the deterministic tests below to validate the system without quota.

## Tests (no API key required)

```bash
uv run python -m pytest tests/test_regression.py -q
```
