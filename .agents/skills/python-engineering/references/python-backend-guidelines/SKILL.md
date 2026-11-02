---
name: python-backend-guidelines
description: FastAPI/Django backend patterns and best practices
version: 1.0.0
triggers:
  - python backend
  - fastapi
  - django
  - flask
  - router
  - endpoint
  - pydantic
---

# Python Backend Development Guidelines

## Overview

This skill provides patterns and best practices for Python backend development with FastAPI, Django, or Flask. Use this when creating APIs, services, or any server-side Python logic.

## Quick Reference

| Pattern | When to Use | Example |
|---------|-------------|---------|
| Router | Group related endpoints | `users_router` |
| Dependency | Shared logic injection | `get_db()`, `get_current_user()` |
| Service | Business logic | `UserService.create_user()` |
| Repository | Data access | `UserRepository.get_by_id()` |
| Schema | Request/Response validation | `UserCreate`, `UserResponse` |

## Project Configuration

<!-- CUSTOMIZE START -->
| Setting | Default | Your Value |
|---------|---------|------------|
| Framework | FastAPI | CHANGE_ME |
| ORM | SQLAlchemy | CHANGE_ME |
| Validation | Pydantic | CHANGE_ME |
| Auth | JWT | CHANGE_ME |
| Base Path | `/api/v1` | CHANGE_ME |
<!-- CUSTOMIZE END -->

## Architecture Overview

```
Request Flow:
Route → Dependency → Controller/Router → Service → Repository → Database
                                              ↓
                                       External APIs
```

### Layer Responsibilities

| Layer | Responsibility | Should NOT Do |
|-------|----------------|---------------|
| **Router** | URL mapping, request handling | Business logic, direct DB |
| **Dependency** | DI, auth, DB sessions | Business logic |
| **Service** | Business logic, orchestration | HTTP concerns, direct SQL |
| **Repository** | Data access, query building | Business rules |
| **Schema** | Validation, serialization | Logic |

## Core Patterns

### Pattern 1: FastAPI Router Structure

```python
# ✅ CORRECT: Clean router with dependency injection
from fastapi import APIRouter, Depends, HTTPException, status
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserResponse
from app.dependencies import get_user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
) -> UserResponse:
    """Create a new user."""
    return await user_service.create(user_data)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
) -> UserResponse:
    """Get user by ID."""
    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
```

```python
# ❌ WRONG: Fat router with business logic and direct DB access
@router.post("/")
async def create_user(user_data: dict, db: Session = Depends(get_db)):
    # Don't put business logic in router
    if db.query(User).filter(User.email == user_data["email"]).first():
        raise HTTPException(status_code=400, detail="Email exists")
    user = User(**user_data)
    db.add(user)
    db.commit()
    return user
```

### Pattern 2: Service Layer

```python
# ✅ CORRECT: Service with business logic
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse
from app.core.exceptions import ConflictError
from app.core.security import hash_password

class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def create(self, data: UserCreate) -> UserResponse:
        # Business logic belongs here
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")

        hashed_password = hash_password(data.password)
        user = await self.user_repo.create(
            email=data.email,
            name=data.name,
            password=hashed_password,
        )
        return UserResponse.model_validate(user)

    async def get_by_id(self, user_id: int) -> UserResponse | None:
        user = await self.user_repo.get_by_id(user_id)
        if user:
            return UserResponse.model_validate(user)
        return None
```

### Pattern 3: Pydantic Schemas

```python
# ✅ CORRECT: Separate schemas for different use cases
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserBase(BaseModel):
    """Shared user fields."""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)

class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    """Schema for updating a user (all fields optional)."""
    email: EmailStr | None = None
    name: str | None = Field(None, min_length=1, max_length=100)

class UserResponse(UserBase):
    """Schema for user responses."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class UserInDB(UserResponse):
    """Internal schema with hashed password."""
    hashed_password: str
```

### Pattern 4: Dependency Injection

```python
# ✅ CORRECT: Dependencies for DI
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService

async def get_db() -> AsyncSession:
    """Get database session."""
    async with get_async_session() as session:
        yield session

def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """Get user repository."""
    return UserRepository(db)

def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository)
) -> UserService:
    """Get user service."""
    return UserService(user_repo)

# Auth dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service)
) -> UserResponse:
    """Get current authenticated user."""
    payload = verify_token(token)
    user = await user_service.get_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

### Pattern 5: Error Handling

```python
# ✅ CORRECT: Custom exceptions with handlers
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)

class ConflictError(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)

# Exception handler
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )
```

## Anti-Patterns

### Don't: Business Logic in Router

```python
# ❌ BAD
@router.post("/users")
async def create_user(data: UserCreate, db: Session = Depends(get_db)):
    # All this should be in a service
    if len(data.password) < 8:
        raise HTTPException(400, "Password too short")
    ...
```

### Don't: Direct DB in Service

```python
# ❌ BAD
class UserService:
    def __init__(self, db: Session):
        self.db = db

    async def get_user(self, id: int):
        return self.db.query(User).filter(User.id == id).first()  # Use repository
```

### Don't: Mutable Default Arguments

```python
# ❌ BAD
def process_items(items: list = []):  # Mutable default!
    items.append("new")
    return items

# ✅ GOOD
def process_items(items: list | None = None):
    if items is None:
        items = []
    items.append("new")
    return items
```

## Resources

| Topic | Link |
|-------|------|
| Routers | [mdc:resources/routers.md] |
| Dependencies | [mdc:resources/dependencies.md] |
| Services | [mdc:resources/services.md] |
| Schemas | [mdc:resources/schemas.md] |
