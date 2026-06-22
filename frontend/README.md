# 제조 설비 진단 어시스턴트 — Frontend

Vite + React (JavaScript/JSX) UI for the Manufacturing Agent FastAPI backend.

## Requirements

- Node 18+ (tested on Node v24 / npm 11)

## Setup

```bash
npm install
```

Copy the environment example and adjust if needed:

```bash
cp .env.example .env
```

`.env`:

```
VITE_API_BASE=http://localhost:8000
```

## How the frontend reaches the backend

By default the app calls the backend **directly** using the full base URL from
`VITE_API_BASE` (read in `src/api.js`, defaulting to `http://localhost:8000`).
The backend already enables CORS for `http://localhost:5173`, so no proxy is
required.

A dev proxy is also configured in `vite.config.js` as an optional alternative:
requests to `/api/*` are forwarded to `VITE_API_BASE` with the `/api` prefix
stripped. The app does not use it by default — it is there if you prefer
same-origin requests during development.

## Scripts

```bash
npm run dev      # start the Vite dev server on http://localhost:5173
npm run build    # production build → dist/
npm run preview  # preview the production build locally
```

## Usage

1. Start the FastAPI backend (default `http://localhost:8000`).
2. Run `npm run dev` and open http://localhost:5173.
3. In the sidebar, click **새 사용자 생성** to create a user (the `user_id` is
   persisted in `localStorage`). Create a **새 대화(thread)** and select it.
4. Type a natural-language question in **질의입력란** (primary). Optionally fill
   numeric values under **데이터 입력란 (선택)** — only filled fields are sent as
   `input_features`; if all are empty, `input_features` is omitted.
5. Press **전송** (or Ctrl/Cmd+Enter). Toggle **debug** to send `?debug=true`
   and view the `trace.gates` / `trace.tasks` box under the answer.

## Project structure

```
frontend/
├── index.html
├── package.json
├── vite.config.js
├── .env.example
├── README.md
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api.js
    ├── styles.css
    └── components/
        ├── Sidebar.jsx
        ├── ChatPanel.jsx
        ├── MessageList.jsx
        ├── AssistantAnswer.jsx
        └── FeatureInputs.jsx
```
