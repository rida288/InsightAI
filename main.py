import asyncio
import traceback
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from app.util.init_db import create_tables
from app.routers.auth import authRouter
from app.routers.admin import adminRouter
from app.routers.project import projectRouter
from app.util.protectRoute import get_current_user
from app.db.schema.user import UserOutput
from fastapi.middleware.cors import CORSMiddleware


async def _prewarm_embedding_model():
    """
    Loads the local embedding model (downloading it on a fresh deploy) and runs
    one embed_query on startup, so the first upload or chat doesn't pay that cost
    and a broken embedding setup shows up in the deploy logs immediately.
    Non-fatal: if the model fails to load, the server still starts normally.
    """
    try:
        from app.service.ingestion import embedding_model
        await asyncio.to_thread(embedding_model.embed_query, "warmup")
        print("[InsightAI] Embedding model pre-warmed successfully.")
    except Exception as e:
        print(f"[InsightAI] Embedding pre-warm failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables and HNSW index
    create_tables()
    # Fire-and-forget: load the embedding model in the background while
    # the server is already accepting health-check pings from Render/UptimeRobot.
    asyncio.create_task(_prewarm_embedding_model())
    yield
    # Cleanup on shutdown (none needed currently)


from fastapi.responses import JSONResponse
from fastapi import Request

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Full details go to the server log only; clients get a generic message so
    # SQL errors, file paths and config details are never exposed.
    print(f"[InsightAI] Unhandled Server Error on {request.method} {request.url.path}:")
    traceback.print_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )

app.include_router(authRouter, tags=["auth"], prefix="/auth")
app.include_router(adminRouter, tags=["admin"], prefix="/admin")
app.include_router(projectRouter, tags=["projects"], prefix="/projects")


@app.get("/health")
def health_check():
    return {"status": "Running..."}


@app.get("/protected")
def read_protected(user: UserOutput = Depends(get_current_user)):
    return {"message": f"Hello {user.first_name} {user.last_name}, you have accessed a protected route!"}