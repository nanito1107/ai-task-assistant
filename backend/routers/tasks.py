"""
Router de tareas - CRUD completo
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import uuid

from database import get_db, Task

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    source: str = "api"
    due_date: Optional[datetime] = None
    telegram_message_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    priority: str
    source: Optional[str]
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status:   Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit:    int = Query(50, le=200),
    offset:   int = Query(0),
    db:       AsyncSession = Depends(get_db)
):
    q = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(id=uuid.uuid4(), **body.model_dump(exclude_none=True))
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Tarea no encontrada")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Tarea no encontrada")
    data = body.model_dump(exclude_none=True)
    if data.get("status") == "completed" and not task.completed_at:
        data["completed_at"] = datetime.utcnow()
    for k, v in data.items():
        setattr(task, k, v)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Tarea no encontrada")
    await db.delete(task)
    await db.commit()
