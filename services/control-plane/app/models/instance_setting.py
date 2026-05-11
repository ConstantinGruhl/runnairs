from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk


class InstanceSetting(Base):
    __tablename__ = "instance_setting"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    value_json: Mapped[dict[str, Any]] = jsonb_col(default=dict)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
