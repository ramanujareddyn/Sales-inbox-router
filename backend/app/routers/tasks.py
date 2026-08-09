from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import Task
from ..schemas import TaskCreate, TaskUpdate, EnumFieldError
from ..config import TEAM_ROSTER, normalize_candidate_id

router = APIRouter()

def _validation_response(error: ValidationError):
    item = error.errors()[0]
    field = item.get("loc", (None,))[0]
    allowed = {
        "assignee_id": ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"],
        "category": ["enterprise_rfp", "smb_enquiry", "marketing", "alliances", "finance", "triage"],
        "priority": ["high", "medium", "low"],
    }
    if field in allowed:
        return JSONResponse(status_code=400, content={
            "error": "invalid_enum_value", "field": field,
            "received": item.get("input"), "allowed": allowed[field],
        })
    return JSONResponse(status_code=400, content={"error": "invalid_payload", "detail": str(error)})


@router.post("/tasks", status_code=201)
def create_task(payload: dict, db: Session = Depends(get_db)):
    try:
        data = TaskCreate(**payload)
    except EnumFieldError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_enum_value", "field": e.field,
                     "received": e.received, "allowed": e.allowed},
        )
    except ValidationError as e:
        return _validation_response(e)
    except ValidationError as e:
        return _validation_response(e)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": "invalid_payload", "detail": str(e)})

    values = data.model_dump()
    existing = db.query(Task).filter(
        Task.candidate_id == values["candidate_id"],
        Task.source_email_id == values["source_email_id"],
    ).first()
    if existing:
        return JSONResponse(status_code=200, content=existing.to_dict())
    task = Task(**values)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "task_id": task.task_id,
        "candidate_id": task.candidate_id,
        "source_email_id": task.source_email_id,
        "created_at": task.created_at.isoformat(),
    }


@router.get("/tasks")
def list_tasks(
    candidate_id: str = Query(...),
    thread_id: Optional[str] = None,
    source_email_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    cid = normalize_candidate_id(candidate_id)
    q = db.query(Task).filter(Task.candidate_id == cid)
    if thread_id:
        q = q.filter(Task.thread_id == thread_id)
    if source_email_id:
        q = q.filter(Task.source_email_id == source_email_id)
    if assignee_id:
        q = q.filter(Task.assignee_id == assignee_id)
    tasks = q.order_by(Task.created_at.asc()).all()
    return [t.to_dict() for t in tasks]


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: dict, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    try:
        data = TaskUpdate(**payload)
    except EnumFieldError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_enum_value", "field": e.field,
                     "received": e.received, "allowed": e.allowed},
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.delete("/tasks/{task_id}", status_code=200)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    db.delete(task)
    db.commit()
    return {"deleted": True, "task_id": task_id}


@router.get("/users")
def list_users():
    return {"team": TEAM_ROSTER}
