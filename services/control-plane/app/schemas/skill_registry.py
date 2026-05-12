from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SkillSourceUpsertRequest(BaseModel):
    repo_url: str
    git_ref: str = Field(default="HEAD")


class SkillTreeEntryPublic(BaseModel):
    path: str
    kind: str
    size_bytes: int | None = None


class SkillSourceSummary(BaseModel):
    slug: str
    display_name: str
    repo_url: str
    git_ref: str
    resolved_commit_sha: str | None
    status: str
    descriptor_format: str | None
    last_synced_at: datetime | None
    last_error: str | None


class SkillSourceDetail(SkillSourceSummary):
    instructions_markdown: str | None
    manifest: dict
    tree: list[SkillTreeEntryPublic]
