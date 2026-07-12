from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.memory import MemoryCreate, MemoryOut
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["Semantic Memory"])

@router.get("", response_model=List[MemoryOut])
async def list_memories(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves all semantic memories and preferences stored for the current user.
    """
    return await MemoryService.get_user_memories(db, current_user.id)

@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(
    schema: MemoryCreate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Records a new semantic fact or preference for the current user.
    """
    return await MemoryService.create_memory(
        db=db,
        user_id=current_user.id,
        category=schema.category,
        content=schema.content,
        importance_score=schema.importance_score
    )

@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes a semantic fact or user preference by ID.
    """
    success = await MemoryService.delete_memory(db, memory_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory fact not found or access denied."
        )
    return {"detail": "Memory fact successfully deleted."}
