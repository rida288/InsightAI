import threading
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from app.service.chat_service import ChatService

# Application-lifetime cache of ChatService instances, keyed by project_id.
# This avoids re-building the LLM client, pandas agent, and LangGraph react
# agent on every single chat request — only the DB-session-dependent search
# tool is rebuilt per request (inside ask_question).
_chat_service_cache: Dict[int, "ChatService"] = {}
# _cache_lock only guards the dicts; each project gets its own build lock so a slow
# first build (S3 download + agent compile) doesn't block other projects.
_cache_lock = threading.Lock()
_build_locks: Dict[int, threading.Lock] = {}


def get_cached_chat_service(project_id: int, file_path: str) -> "ChatService":
    """
    Returns a cached ChatService for the given project, constructing it once
    and reusing it for all subsequent requests to the same project.
    """
    with _cache_lock:
        service = _chat_service_cache.get(project_id)
        if service is not None:
            return service
        build_lock = _build_locks.setdefault(project_id, threading.Lock())

    with build_lock:
        # Another request may have finished building while we waited
        with _cache_lock:
            service = _chat_service_cache.get(project_id)
        if service is not None:
            return service

        from app.service.chat_service import ChatService
        print(f"[InsightAI] Building ChatService for project {project_id} (first request)...")
        service = ChatService(project_id=project_id, file_path=file_path)
        with _cache_lock:
            _chat_service_cache[project_id] = service
        return service


def invalidate_chat_service(project_id: int) -> None:
    """
    Removes the cached ChatService for a project.
    Must be called when a project is deleted so stale state is cleared.
    """
    with _cache_lock:
        removed = _chat_service_cache.pop(project_id, None)
        _build_locks.pop(project_id, None)
        if removed:
            print(f"[InsightAI] Evicted ChatService cache for deleted project {project_id}")
