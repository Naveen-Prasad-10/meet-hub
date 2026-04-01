"""Main application entry point."""

import os

from dotenv import load_dotenv

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.settings import get_settings
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db, init_db
from app.schemas import PostCreate, PostResponse, PostUpdate, UserCreate, UserResponse, UserUpdate

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database tables on startup
    init_db()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="A Python API built with Better Fullstack",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to meet-hub!"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# User endpoints
@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user."""
    existing = crud.get_user_by_email(db, user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user)


@app.get("/users", response_model=list[UserResponse])
async def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all users."""
    return crud.get_users(db, skip=skip, limit=limit)


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a user by ID."""
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    """Update a user."""
    updated = crud.update_user(db, user_id, user)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Delete a user."""
    if not crud.delete_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")


# Post endpoints
@app.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(post: PostCreate, db: Session = Depends(get_db)):
    """Create a new post."""
    # Verify author exists
    if crud.get_user(db, post.author_id) is None:
        raise HTTPException(status_code=400, detail="Author not found")
    return crud.create_post(db, post)


@app.get("/posts", response_model=list[PostResponse])
async def list_posts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all posts."""
    return crud.get_posts(db, skip=skip, limit=limit)


@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Session = Depends(get_db)):
    """Get a post by ID."""
    post = crud.get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.patch("/posts/{post_id}", response_model=PostResponse)
async def update_post(post_id: int, post: PostUpdate, db: Session = Depends(get_db)):
    """Update a post."""
    updated = crud.update_post(db, post_id, post)
    if updated is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return updated


@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(post_id: int, db: Session = Depends(get_db)):
    """Delete a post."""
    if not crud.delete_post(db, post_id):
        raise HTTPException(status_code=404, detail="Post not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
