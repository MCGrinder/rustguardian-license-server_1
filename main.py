from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Activation, License

app = FastAPI(title="RustGuardian License API", version="2.0.0")

Base.metadata.create_all(bind=engine)

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-me-now")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def require_admin(x_admin_secret: Optional[str] = Header(default=None)) -> None:
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def generate_license_key() -> str:
    parts = []
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(4):
        parts.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "RG-" + "-".join(parts)


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class ValidateLicenseRequest(BaseModel):
    license_key: str = Field(min_length=5, max_length=64)
    server_id: str = Field(min_length=1, max_length=64)
    app_version: Optional[str] = None


class ValidateLicenseResponse(BaseModel):
    valid: bool
    message: str
    license_key: Optional[str] = None
    plan: Optional[str] = None
    server_limit: Optional[int] = None
    bound_servers: list[str] = []
    expires_at: Optional[str] = None
    last_checked_at: Optional[str] = None


class CreateLicenseRequest(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    plan: str = "single_server"
    server_limit: int = Field(default=1, ge=1, le=1000)
    duration_days: int = Field(default=30, ge=1, le=3650)
    notes: Optional[str] = None


class ExtendLicenseRequest(BaseModel):
    duration_days: int = Field(ge=1, le=3650)


class RevokeLicenseRequest(BaseModel):
    reason: Optional[str] = None


class ResetBindingsRequest(BaseModel):
    reason: Optional[str] = None


class LicenseOut(BaseModel):
    license_key: str
    status: str
    plan: str
    server_limit: int
    customer_name: Optional[str]
    customer_email: Optional[str]
    bound_servers: list[str]
    expires_at: str
    notes: Optional[str]
    created_at: str
    updated_at: str


def license_to_out(lic: License) -> LicenseOut:
    return LicenseOut(
        license_key=lic.license_key,
        status=lic.status,
        plan=lic.plan,
        server_limit=lic.server_limit,
        customer_name=lic.customer_name,
        customer_email=lic.customer_email,
        bound_servers=lic.bound_servers_list(),
        expires_at=normalize_dt(lic.expires_at).isoformat(),
        notes=lic.notes,
        created_at=normalize_dt(lic.created_at).isoformat(),
        updated_at=normalize_dt(lic.updated_at).isoformat(),
    )


@app.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    return HealthResponse(ok=True, service="RustGuardian License API", version=app.version)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="RustGuardian License API", version=app.version)


@app.post("/validate-license", response_model=ValidateLicenseResponse)
def validate_license(data: ValidateLicenseRequest, db: Session = Depends(get_db)) -> ValidateLicenseResponse:
    stmt = select(License).where(License.license_key == data.license_key)
    lic = db.scalar(stmt)

    if not lic:
        return ValidateLicenseResponse(valid=False, message="License not found")

    now = utcnow()
    lic.last_checked_at = now

    if lic.status != "active":
        db.commit()
        return ValidateLicenseResponse(valid=False, message=f"License {lic.status}")

    if normalize_dt(lic.expires_at) < now:
        lic.status = "expired"
        lic.updated_at = now
        db.commit()
        return ValidateLicenseResponse(valid=False, message="License expired")

    bound_servers = lic.bound_servers_list()

    if data.server_id not in bound_servers:
        if len(bound_servers) >= lic.server_limit:
            db.commit()
            return ValidateLicenseResponse(
                valid=False,
                message="Server limit reached",
                license_key=lic.license_key,
                plan=lic.plan,
                server_limit=lic.server_limit,
                bound_servers=bound_servers,
                expires_at=normalize_dt(lic.expires_at).isoformat(),
                last_checked_at=now.isoformat(),
            )
        bound_servers.append(data.server_id)
        lic.set_bound_servers(bound_servers)

        activation = Activation(
            license_key=lic.license_key,
            server_id=data.server_id,
            app_version=data.app_version,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(activation)
    else:
        activation = db.scalar(
            select(Activation).where(
                Activation.license_key == lic.license_key,
                Activation.server_id == data.server_id,
            )
        )
        if activation:
            activation.last_seen_at = now
            activation.app_version = data.app_version

    lic.updated_at = now
    db.commit()
    db.refresh(lic)

    return ValidateLicenseResponse(
        valid=True,
        message="License active",
        license_key=lic.license_key,
        plan=lic.plan,
        server_limit=lic.server_limit,
        bound_servers=lic.bound_servers_list(),
        expires_at=normalize_dt(lic.expires_at).isoformat(),
        last_checked_at=now.isoformat(),
    )


@app.post("/admin/licenses", response_model=LicenseOut, dependencies=[Depends(require_admin)])
def create_license(data: CreateLicenseRequest, db: Session = Depends(get_db)) -> LicenseOut:
    now = utcnow()
    license_key = generate_license_key()

    lic = License(
        license_key=license_key,
        status="active",
        plan=data.plan,
        server_limit=data.server_limit,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        expires_at=now + timedelta(days=data.duration_days),
        notes=data.notes,
        created_at=now,
        updated_at=now,
        last_checked_at=None,
        bound_servers_json="[]",
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return license_to_out(lic)


@app.get("/admin/licenses", response_model=list[LicenseOut], dependencies=[Depends(require_admin)])
def list_licenses(db: Session = Depends(get_db)) -> list[LicenseOut]:
    rows = db.scalars(select(License).order_by(License.created_at.desc())).all()
    return [license_to_out(x) for x in rows]


@app.get("/admin/licenses/{license_key}", response_model=LicenseOut, dependencies=[Depends(require_admin)])
def get_license(license_key: str, db: Session = Depends(get_db)) -> LicenseOut:
    lic = db.scalar(select(License).where(License.license_key == license_key))
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return license_to_out(lic)


@app.post("/admin/licenses/{license_key}/extend", response_model=LicenseOut, dependencies=[Depends(require_admin)])
def extend_license(license_key: str, data: ExtendLicenseRequest, db: Session = Depends(get_db)) -> LicenseOut:
    lic = db.scalar(select(License).where(License.license_key == license_key))
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    start_from = max(normalize_dt(lic.expires_at), utcnow())
    lic.expires_at = start_from + timedelta(days=data.duration_days)
    if lic.status == "expired":
        lic.status = "active"
    lic.updated_at = utcnow()
    db.commit()
    db.refresh(lic)
    return license_to_out(lic)


@app.post("/admin/licenses/{license_key}/revoke", response_model=LicenseOut, dependencies=[Depends(require_admin)])
def revoke_license(license_key: str, data: RevokeLicenseRequest, db: Session = Depends(get_db)) -> LicenseOut:
    lic = db.scalar(select(License).where(License.license_key == license_key))
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    lic.status = "revoked"
    if data.reason:
        lic.notes = f"{lic.notes or ''}\nRevoked: {data.reason}".strip()
    lic.updated_at = utcnow()
    db.commit()
    db.refresh(lic)
    return license_to_out(lic)


@app.post("/admin/licenses/{license_key}/reset-bindings", response_model=LicenseOut, dependencies=[Depends(require_admin)])
def reset_bindings(license_key: str, data: ResetBindingsRequest, db: Session = Depends(get_db)) -> LicenseOut:
    lic = db.scalar(select(License).where(License.license_key == license_key))
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    lic.set_bound_servers([])
    if data.reason:
        lic.notes = f"{lic.notes or ''}\nBindings reset: {data.reason}".strip()
    lic.updated_at = utcnow()

    rows = db.scalars(select(Activation).where(Activation.license_key == license_key)).all()
    for row in rows:
        db.delete(row)

    db.commit()
    db.refresh(lic)
    return license_to_out(lic)
