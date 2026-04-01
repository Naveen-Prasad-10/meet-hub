"""CRUD operations for database models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Post, User
from app.schemas import PostCreate, PostUpdate, UserCreate, UserUpdate


# User CRUD operations
def get_user(db: Session, user_id: int) -> User | None:
    """Get a user by ID."""
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Get a user by email."""
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Get a list of users with pagination."""
    stmt = select(User).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def create_user(db: Session, user: UserCreate) -> User:
    """Create a new user."""
    db_user = User(email=user.email, name=user.name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user: UserUpdate) -> User | None:
    """Update a user."""
    db_user = get_user(db, user_id)
    if db_user is None:
        return None

    update_data = user.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Delete a user."""
    db_user = get_user(db, user_id)
    if db_user is None:
        return False

    db.delete(db_user)
    db.commit()
    return True


# Post CRUD operations
def get_post(db: Session, post_id: int) -> Post | None:
    """Get a post by ID."""
    return db.get(Post, post_id)


def get_posts(db: Session, skip: int = 0, limit: int = 100) -> list[Post]:
    """Get a list of posts with pagination."""
    stmt = select(Post).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_posts_by_author(db: Session, author_id: int) -> list[Post]:
    """Get all posts by an author."""
    stmt = select(Post).where(Post.author_id == author_id)
    return list(db.execute(stmt).scalars().all())


def create_post(db: Session, post: PostCreate) -> Post:
    """Create a new post."""
    db_post = Post(title=post.title, content=post.content, author_id=post.author_id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post


def update_post(db: Session, post_id: int, post: PostUpdate) -> Post | None:
    """Update a post."""
    db_post = get_post(db, post_id)
    if db_post is None:
        return None

    update_data = post.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_post, field, value)

    db.commit()
    db.refresh(db_post)
    return db_post


def delete_post(db: Session, post_id: int) -> bool:
    """Delete a post."""
    db_post = get_post(db, post_id)
    if db_post is None:
        return False

    db.delete(db_post)
    db.commit()
    return True
