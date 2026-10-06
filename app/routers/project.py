import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.db.schema.user import UserOutput
from app.util.protectRoute import get_current_user, get_current_admin
from app.service.projectService import ProjectService
from app.core.service_cache import get_cached_chat_service, invalidate_chat_service

projectRouter = APIRouter()

from pydantic import BaseModel
from datetime import datetime


class ProjectOutput(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    file_name: str
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Background ingestion helper
# ---------------------------------------------------------------------------

def _run_ingestion_background(project_id: int, file_path: str) -> None:
    """
    Embeds a project's spreadsheet into pgvector.
    Runs in a background task AFTER the HTTP response is already sent,
    so the upload endpoint returns immediately to the user.
    """
    from app.core.database import SessionLocal
    from app.service.ingestion import IngestionService
    from app.tools.math_tool import _load_dataframe
    from app.core.service_cache import get_cached_chat_service

    db = SessionLocal()
    try:
        print(f"[InsightAI] Starting background ingestion for project {project_id}...")
        _load_dataframe(file_path)
        get_cached_chat_service(project_id=project_id, file_path=file_path)
        total = IngestionService(db=db).process_and_embed_project_data(
            project_id=project_id,
            file_path=file_path,
        )
        print(f"[InsightAI] Ingestion complete for project {project_id} — {total} rows embedded.")
    except Exception as e:
        print(f"[InsightAI] Ingestion FAILED for project {project_id}: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@projectRouter.post("", response_model=ProjectOutput, status_code=201)
def create_project(
    name: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_db),
    current_user: UserOutput = Depends(get_current_user),
):
    try:
        project = ProjectService(session=session).create_project(
            name=name,
            description=description,
            file=file,
            owner_id=current_user.id,
        )
        # Kick off embedding ingestion in the background — response returns
        # immediately without waiting for all rows to be embedded.
        if background_tasks is not None:
            background_tasks.add_task(
                _run_ingestion_background, project.id, project.file_path
            )
        return project
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@projectRouter.get("", response_model=List[ProjectOutput])
def get_user_projects(
    session: Session = Depends(get_db),
    current_user: UserOutput = Depends(get_current_user),
):
    try:
        return ProjectService(session=session).get_projects_by_owner(owner_id=current_user.id)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@projectRouter.get("/all", response_model=List[ProjectOutput])
def get_all_projects(
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin),
):
    try:
        return ProjectService(session=session).get_all_projects()
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@projectRouter.get("/{project_id}/data")
def get_project_data(
    project_id: int,
    session: Session = Depends(get_db),
    current_user: UserOutput = Depends(get_current_user),
):
    try:
        is_admin = current_user.role == "Admin"
        return ProjectService(session=session).parse_project_data(
            project_id=project_id,
            current_user_id=current_user.id,
            is_admin=is_admin,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@projectRouter.delete("/{project_id}")
def delete_project(
    project_id: int,
    session: Session = Depends(get_db),
    current_user: UserOutput = Depends(get_current_user),
):
    try:
        is_admin = current_user.role == "Admin"
        result = ProjectService(session=session).delete_project(
            project_id=project_id,
            current_user_id=current_user.id,
            is_admin=is_admin,
        )
        # Evict the stale ChatService cache entry for this project
        invalidate_chat_service(project_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


class ChatRequest(BaseModel):
    message: str


@projectRouter.post("/{project_id}/chat")
async def chat_with_project(
    project_id: int,
    request: ChatRequest,
    session: Session = Depends(get_db),
    current_user: UserOutput = Depends(get_current_user),
):
    from app.db.repository.projectRepo import ProjectRepository

    try:
        is_admin = current_user.role == "Admin"
        project = ProjectRepository(session=session).get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.owner_id != current_user.id and not is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to access this project")

        def get_service_and_ask():
            chat_service = get_cached_chat_service(
                project_id=project_id,
                file_path=project.file_path,
            )
            return chat_service.ask_question(request.message)

        # Run the synchronous agent in a thread pool so it does NOT block
        # FastAPI's async event loop. The session is NOT passed in —
        # chat_service.ask_question creates its own thread-local DB session.
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(get_service_and_ask),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="The query timed out. Try a simpler or more specific question.",
            )

        return {"answer": answer}
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
