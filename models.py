from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class LicenseMixin:
    def bound_servers_list(self) -> list[str]:
        try:
            data = json.loads(self.bound_servers_json or "[]")
            return [str(x) for x in data]
        except Exception:
            return []

    def set_bound_servers(self, values: list[str]) -> None:
        self.bound_servers_json = json.dumps(sorted(set(str(x) for x in values)))


from database import Base


class License(Base, LicenseMixin):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    plan: Mapped[str] = mapped_column(String(64), default="single_server")
    server_limit: Mapped[int] = mapped_column(Integer, default=1)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bound_servers_json: Mapped[str] = mapped_column(Text, default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Activation(Base):
    __tablename__ = "activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_key: Mapped[str] = mapped_column(String(64), index=True)
    server_id: Mapped[str] = mapped_column(String(64), index=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
