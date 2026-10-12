# InsightAI

**Upload a spreadsheet, explore it in the browser, and ask questions about it in plain English.**

InsightAI is a full-stack web app for working with CSV and Excel files. Users upload a spreadsheet, browse it in an Excel-like viewer with search, sorting and column filters, and chat with an AI analyst that answers questions about the data. The AI runs real pandas calculations for numeric questions and uses semantic search for fuzzy text lookups. An admin panel handles account approval and user management.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started (Local Development)](#getting-started-local-development)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)

---

## Features

### Spreadsheet viewer
- Upload `.csv` or `.xlsx` files (up to 5 MB)
- Multi-sheet Excel support with sheet tabs
- Global search across all cells
- Click-to-sort columns (numeric-aware)
- Excel-style per-column filter dropdowns with "Select All"
- Pagination with adjustable rows per page

### AI chat analyst
- Ask questions in plain English, such as *"What is the average Net Sales per customer type?"*
- **Calculations:** the AI writes pandas code that runs against your data in a sandbox, so answers come from actual computation rather than guesses
- **Semantic search:** finds rows by meaning, not just exact keywords, using vector embeddings stored in PostgreSQL (pgvector)
- Answers are rendered as Markdown (tables, lists, bold text)

### Accounts and administration
- Sign up and log in with JWT authentication
- New accounts need admin approval before they can log in
- **The first user to sign up automatically becomes an approved Admin**
- Admins can approve, suspend, edit and delete users, create pre-approved users with a role, and view every project
- Suspending a user immediately revokes access, including tokens they already have
- Logout revokes the token on the server (token blacklist)

---

## How It Works

```mermaid
flowchart LR
    U[Browser<br/>React + Vite] -->|REST + JWT| API[FastAPI backend]
    API -->|users, projects,<br/>embeddings| DB[(PostgreSQL<br/>+ pgvector)]
    API -->|upload / download<br/>spreadsheets| B2[(Backblaze B2<br/>S3-compatible)]
    API -->|chat completions| G[Google Gemini]
    API -->|local ONNX model| E[fastembed<br/>bge-small-en-v1.5]
```

### Upload flow
1. The file is validated (type and size) and uploaded to Backblaze B2 under a random UUID filename.
2. A project record is saved in PostgreSQL and the API responds immediately.
3. A **low-priority background thread** then:
   - turns every row into text (`Column: value | Column: value ...`)
   - embeds the rows in batches with a **local** embedding model (`BAAI/bge-small-en-v1.5` via fastembed/ONNX, 384 dimensions)
   - saves the vectors to the `project_embeddings` table, which has an HNSW index for fast cosine search

### Chat flow
1. The question goes to a **LangGraph ReAct agent** backed by Google Gemini.
2. The agent's system prompt includes the dataset schema (column names, types and sample rows), so simple schema questions are answered directly.
3. For anything else, the agent picks a tool:
   - **`execute_pandas_code`** runs sandboxed pandas code against the DataFrame for maths, counts, grouping and filtering
   - **`semantic_search`** embeds the question and returns the 5 closest rows from pgvector
4. Each project's agent is built once and cached in memory, so later questions skip the setup cost.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, React Router, react-markdown, jwt-decode, Oxlint |
| Backend | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 |
| Database | PostgreSQL with the pgvector extension (hosted on Supabase) |
| File storage | Backblaze B2 (S3-compatible API via boto3) |
| AI / LLM | Google Gemini (`gemini-3.6-flash` by default) via LangChain and LangGraph |
| Embeddings | fastembed (ONNX Runtime), `BAAI/bge-small-en-v1.5`, runs locally |
| Data | pandas, openpyxl |
| Auth | PyJWT, bcrypt |
| Hosting | Render (API), Vercel (frontend), Supabase (database) |

---

## Project Structure

```
.
├── main.py                       # FastAPI app: lifespan, CORS, error handler, routers
├── requirements.txt              # Pinned Python dependencies
├── app/
│   ├── core/
│   │   ├── database.py           # SQLAlchemy engine/session, DATABASE_URL handling
│   │   ├── service_cache.py      # Per-project cache of chat agents
│   │   ├── security/
│   │   │   ├── authHandler.py    # JWT sign/verify
│   │   │   └── hashHelper.py     # bcrypt password hashing
│   │   └── storage/
│   │       └── s3_client.py      # Backblaze B2 upload/download/delete
│   ├── db/
│   │   ├── models/               # User, Project, ProjectEmbedding, TokenBlacklist
│   │   ├── repository/           # Data-access layer
│   │   └── schema/               # Pydantic request/response models
│   ├── routers/
│   │   ├── auth.py               # /auth: signup, login, logout
│   │   ├── admin.py              # /admin: user management
│   │   └── project.py            # /projects: upload, view, delete, chat
│   ├── service/
│   │   ├── userService.py        # Auth and user business logic
│   │   ├── projectService.py     # Upload validation, spreadsheet parsing
│   │   ├── ingestion.py          # Row extraction and embedding
│   │   └── chat_service.py       # Gemini + LangGraph agent
│   ├── tools/
│   │   ├── math_tool.py          # Sandboxed pandas execution tool
│   │   └── search_tool.py        # pgvector semantic search tool
│   └── util/
│       ├── init_db.py            # Creates tables, pgvector extension, HNSW index
│       └── protectRoute.py       # Auth dependencies (current user / admin)
└── frontend/
    ├── vercel.json               # SPA rewrite rule
    └── src/
        ├── App.jsx               # Routes
        ├── services/api.js       # API client (timeouts, error handling)
        ├── pages/                # Login, Signup, Dashboard
        └── components/
            └── SpreadsheetViewer.jsx  # Grid, filters, pagination, chat panel
```

---

## Getting Started (Local Development)

### Prerequisites
- **Python 3.14**
- **Node.js 20+** and npm
- **PostgreSQL with pgvector.** The easiest option is Docker:
  ```bash
  docker run -d --name insightai-db -p 5432:5432 \
    -e POSTGRES_PASSWORD=pwd pgvector/pgvector:pg17
  ```
  A free Supabase project also works; pgvector is available there.
- A **Backblaze B2** bucket and application key
- A **Google Gemini API key** from [Google AI Studio](https://aistudio.google.com/)

### 1. Backend

```bash
# from the repository root
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repository root (see [Environment Variables](#environment-variables)):

```env
DATABASE_URL=postgresql://postgres:pwd@127.0.0.1:5432/postgres
JWT_SECRET=change-me-to-a-long-random-string
JWT_ALGORITHM=HS256
GOOGLE_API_KEY=your-gemini-api-key
B2_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
B2_ACCESS_KEY_ID=your-key-id
B2_SECRET_ACCESS_KEY=your-application-key
B2_BUCKET_NAME=your-bucket-name
```

Start the API:

```bash
uvicorn main:app --reload
```

On startup the app creates the `vector` extension, all tables and the HNSW index automatically. It also downloads the embedding model (~67 MB) the first time. Interactive API docs are at **http://localhost:8000/docs**.

### 2. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env` if your API isn't at `http://localhost:8000`:

```env
VITE_API_URL=http://localhost:8000
```

```bash
npm run dev      # dev server (http://localhost:5173)
npm run build    # production build into frontend/dist
npm run lint     # Oxlint
```

### 3. First login
Sign up through the UI. **The first account becomes an approved Admin automatically.** Every later sign-up must be approved by an admin from the dashboard before that user can log in.

---

## Environment Variables

### Backend

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. `postgres://` and `postgresql://` are converted to the psycopg2 driver automatically. Defaults to a local database if unset. |
| `JWT_SECRET` | Yes | Secret used to sign login tokens. Use a long random string. |
| `JWT_ALGORITHM` | Yes | JWT signing algorithm, e.g. `HS256`. |
| `GOOGLE_API_KEY` | Yes | Gemini API key for the chat agent. |
| `B2_ENDPOINT_URL` | Yes | Backblaze B2 S3 endpoint, e.g. `https://s3.us-east-005.backblazeb2.com`. |
| `B2_ACCESS_KEY_ID` | Yes | B2 application key ID. |
| `B2_SECRET_ACCESS_KEY` | Yes | B2 application key. |
| `B2_BUCKET_NAME` | Yes | Bucket that stores uploaded spreadsheets. |
| `GEMINI_MODEL` | No | Overrides the chat model (default `gemini-3.6-flash`). Google retires model versions periodically, so changing this variable is enough to switch models. |

### Frontend

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | In production | Base URL of the backend. Defaults to `http://localhost:8000`. |

> Never commit `.env` files. `.env` is already in `.gitignore`.

---

## API Reference

All endpoints except signup, login and health require an `Authorization: Bearer <token>` header. Full interactive docs are served at `/docs`.

### Auth: `/auth`
| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/signup` | Create an account (pending approval; the first user becomes Admin) |
| `POST` | `/auth/login` | Returns `{ "token": "..." }`. Tokens are valid for 7 days. |
| `POST` | `/auth/logout` | Revokes the current token |

### Projects: `/projects`
| Method | Path | Access | Description |
|---|---|---|---|
| `POST` | `/projects` | User | Upload a spreadsheet (multipart: `name`, `description`, `file`) |
| `GET` | `/projects` | User | List your projects |
| `GET` | `/projects/all` | Admin | List all projects |
| `GET` | `/projects/{id}/data` | Owner / Admin | Parsed sheets: headers and rows (max 10,000 rows per sheet) |
| `DELETE` | `/projects/{id}` | Owner / Admin | Delete the project, its file and its embeddings |
| `POST` | `/projects/{id}/chat` | Owner / Admin | `{ "message": "..." }` → `{ "answer": "..." }`, 45 s limit |

### Admin: `/admin` (Admin only)
| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/users` | List all users |
| `GET` | `/admin/users/pending` | List users awaiting approval |
| `POST` | `/admin/users` | Create a pre-approved user (`role`: `User` or `Admin`) |
| `PUT` | `/admin/users/{id}` | Update name, email or password |
| `PUT` | `/admin/users/{id}/approve` | Approve a user |
| `PUT` | `/admin/users/{id}/suspend` | Suspend a user (not yourself) |
| `DELETE` | `/admin/users/{id}` | Delete a user and all their projects and files (not yourself) |

### Misc
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (used for uptime pings) |
| `GET` | `/protected` | Test endpoint that returns the current user's name |

---

## Deployment

The live setup uses **Render** (API), **Vercel** (frontend), **Supabase** (PostgreSQL + pgvector) and **Backblaze B2** (files).

### Database: Supabase
1. Create a project. pgvector is available, and the app enables it on startup.
2. Open **Connect** and copy the **Session pooler** connection string:
   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
   Don't use the *Direct connection* host (`db.<ref>.supabase.co`). It is IPv6-only and Render can't reach it.
3. **URL-encode special characters in the password**: `@` → `%40`, `#` → `%23`, `*` → `%2A`, `^` → `%5E`. Leave out the `[ ]` placeholder brackets.

### Backend: Render
1. Create a **Web Service** from this repository.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add the backend [environment variables](#environment-variables). `DATABASE_URL` is the Supabase session-pooler URL.
5. After deploying, check the logs for:
   ```
   [InsightAI] Database tables and HNSW index verified.
   [InsightAI] Embedding model pre-warmed successfully.
   ```

**Free-tier notes (512 MB RAM, ~0.1 CPU):**
- The local embedding model uses about 170 MB loaded. The whole app peaks around 410–430 MB while embedding.
- Embedding runs on a low-priority thread so chat stays responsive. Large files can still take several minutes to finish embedding.
- Free instances sleep when idle. An uptime monitor pinging `/health` keeps them awake.

### Frontend: Vercel
1. Import the repository and set the **Root Directory** to `frontend`.
2. Framework preset: **Vite** (build `npm run build`, output `dist`).
3. Set `VITE_API_URL` to your Render URL, e.g. `https://your-api.onrender.com`.
4. `vercel.json` already rewrites all routes to `index.html` so client-side routing works on refresh.

---

## Security

- **Passwords** are hashed with bcrypt and never returned by the API.
- **Login** returns the same error for an unknown email and a wrong password, so it can't be used to discover which emails have accounts.
- **Authorization:** every protected request re-checks that the user still exists and is approved, so suspension takes effect immediately. Admins cannot suspend or delete their own account, which means at least one admin always remains.
- **Error responses** never include internal details. Full tracebacks go to the server logs only.
- **AI code sandbox:** pandas code written by the model is checked before it runs. Imports, dunder (`__x__`) access, file and network I/O (`read_*`, `to_csv`, `np.load`, …), string evaluation (`eval`, `query`, `format`) and dangerous built-ins (`open`, `getattr`, `__import__`) are all rejected. The code runs on a copy of the data. This is defence-in-depth inside the API process, not a full OS-level sandbox.
- **Files** are stored under random UUID names. Only the project owner or an admin can read, chat with or delete a project.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SSL connection has been closed unexpectedly` on startup | The database is unreachable: expired or suspended, the wrong host, or blocked by an IP allowlist. Check `DATABASE_URL` on Render and the database's status. |
| `Error parsing file: 404 ... NoSuchKey` | The project's file isn't in the B2 bucket, often because a project was copied from another database or bucket. Delete the project and upload the file again. |
| `models/gemini-x is no longer available` | Google retired that model. Set `GEMINI_MODEL` to a current model (see Google's [deprecations page](https://ai.google.dev/gemini-api/docs/deprecations)). |
| Chat says the model is busy, or a rate limit was reached | Gemini returned 503/429. Wait a moment and retry, or switch `GEMINI_MODEL`. |
| Chat times out (504) | Look for `[InsightAI]` timing lines in the server logs (`answered in …`, `chat service setup took …`). Heavy embedding work or a slow model are the usual causes. |
| Semantic search finds nothing for a new upload | Embedding is still running in the background. Watch for `embedded batch X/Y` and `Ingestion complete` in the logs. |
| Out-of-memory restarts on Render | The free tier is close to its limit while embedding. Upload smaller files or move to a larger instance. |

---

## Known Limitations

- Background embedding failures are only reported in the server logs; the UI doesn't yet show embedding status.
- The token blacklist grows over time. Expired tokens aren't pruned yet.
- The chat agent and parsed-data caches live in process memory, so they reset on restart and aren't shared across multiple instances.
- Uploads are limited to 5 MB, and the viewer shows at most 10,000 rows per sheet.
- `create_react_agent` is deprecated in LangGraph 1.x; it still works with the pinned versions.
