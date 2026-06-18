import time

from typing import Callable, Awaitable
from sqlalchemy import inspect
from fastapi import Response
from starlette.background import BackgroundTask, BackgroundTasks
from loguru import logger

from opengsync_db import models, AsyncSession

from . import audit, runtime

async def state_initialization_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    runtime.RequestState.apply_defaults(request.state)
    response = await call_next(request)
    return response

async def add_background_task(response: Response, task: BackgroundTask):
    if response.background is None:
        response.background = task
    elif isinstance(response.background, BackgroundTasks):
        response.background.add_task(task.func, *task.args, **task.kwargs)
    else:
        old_task = response.background
        combined_tasks = BackgroundTasks()
        combined_tasks.add_task(old_task.func, *old_task.args, **old_task.kwargs)
        combined_tasks.add_task(task.func, *task.args, **task.kwargs)
        response.background = combined_tasks


async def timing_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    start_time = time.time()
    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

async def __save_audit_log(request: runtime.Request, audit: audit.AuditLogger, user_id, ip: str, agent: str, status_code: int):
    print(f"Audit Log - Route: {audit.route}, Method: {audit.method}, User ID: {user_id}, IP: {ip}, Agent: {agent}, Status Code: {status_code}", flush=True)
    # async with request.app.state.db_handler.get_session() as session:
    #     await session.save(models.AuditLog(
    #         user_id=user_id,
    #         method=audit.method,
    #         route=audit.route,
    #         metadata=audit.metadata,
    #         ip=ip,
    #         status_code=status_code,
    #         agent=agent
    #     ))
    #     await session.commit()

async def audit_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    response = await call_next(request)
    
    audit = request.state.audit
    
    if audit is not None:
        current_user = getattr(request.state, "current_user", None)
        
        user_id = None
        if isinstance(current_user, models.User):
            user_id = inspect(current_user).dict["id"]

        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "1.1.1.1")
        agent = request.headers.get("user-agent", "unknown")
        
        await add_background_task(
            response,
            BackgroundTask(
                __save_audit_log, 
                request=request,
                audit=audit, 
                user_id=user_id, 
                ip=ip, 
                agent=agent, 
                status_code=response.status_code
            )
        )            
    return response


async def db_session_cleanup_middleware(request: runtime.Request, call_next: Callable[[runtime.Request], Awaitable[Response]]):
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        session: AsyncSession | None = getattr(request.state, "db_session", None)
        
        if session is not None:
            try:
                await session.commit()
            finally:
                await session.close()
