"""Sign-up / sign-in. The first account ever created becomes the admin."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..app_config import get_config
from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auths", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


class SignUpBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class SignInBody(BaseModel):
    email: str
    password: str


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PasswordBody(BaseModel):
    password: str
    new_password: str = Field(min_length=8, max_length=256)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid email address")
    return email


def session_response(user: User) -> dict:
    return {"token": create_token(user.id), "token_type": "Bearer", "user": user.public()}


@router.post("/signup")
def signup(body: SignUpBody, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    user_count = db.query(func.count(User.id)).scalar() or 0
    cfg = get_config(db)

    if user_count > 0 and not cfg["enable_signup"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "New sign-ups are disabled. Ask an admin for an account.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account with this email already exists")

    role = "admin" if user_count == 0 else cfg["default_user_role"]
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password), role=role)
    db.add(user)
    db.commit()
    return session_response(user)


@router.post("/signin")
def signin(body: SignInBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect email or password")
    return session_response(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {**user.public(), "settings": user.settings or {}}


@router.put("/me/profile")
def update_profile(body: ProfileBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.name = body.name.strip()
    db.commit()
    return user.public()


@router.put("/me/password")
def update_password(body: PasswordBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.get("/me/settings")
def get_settings(user: User = Depends(get_current_user)):
    return user.settings or {}


@router.put("/me/settings")
def put_settings(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = {
        "theme",
        "system_prompt",
        "default_model",
        "cowork_default_model",
        "cowork_instructions",
        "cowork_approval_mode",
    }
    merged = dict(user.settings or {})
    for key, value in body.items():
        if key in allowed:
            merged[key] = value
    user.settings = merged
    db.commit()
    return merged
