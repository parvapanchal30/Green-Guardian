from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class EvidenceOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    observation_id: uuid.UUID | None
    issue_id: uuid.UUID | None
    uploaded_by: uuid.UUID
    original_filename: str | None
    content_type: str
    size_bytes: int
    sha256: str
    width: int
    height: int
    caption: str | None
    created_at: datetime
    # Authenticated download path (relative to the API prefix). The image is not publicly addressable.
    content_path: str
