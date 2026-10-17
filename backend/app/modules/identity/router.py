from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import current_user

from . import service
from .models import User
from .schemas import LoginIn, MeUpdate, RefreshIn, RegisterIn, TokenPair, UserOut

router = APIRouter(tags=["identity"])


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return service.register(db, email=data.email, password=data.password, name=data.name, settings=settings)


@router.post("/auth/login", response_model=TokenPair)
def login(data: LoginIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return service.login(db, email=data.email, password=data.password, settings=settings)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(data: RefreshIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return service.refresh(db, refresh_token=data.refresh_token, settings=settings)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    service.logout(db, refresh_token=data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(data: MeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.update_me(db, user, data)
