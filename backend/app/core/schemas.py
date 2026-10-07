"""Shared Pydantic base and validators for request bodies."""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_JSON_BYTES = 10_000
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class StrictModel(BaseModel):
    """Request bodies reject unknown fields, so typos fail loudly instead of being silently ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _small_json(value: dict | list) -> dict | list:
    if len(json.dumps(value, default=str)) > MAX_JSON_BYTES:
        raise ValueError(f"JSON value larger than {MAX_JSON_BYTES} bytes")
    return value


SmallDict = Annotated[dict, AfterValidator(_small_json)]


class Attachment(StrictModel):
    """Evidence/photo METADATA. File upload and storage arrive with the storage slice; until then only a reference
    (https URL or opaque storage key) plus descriptive fields are stored."""

    name: str = Field(min_length=1, max_length=200)
    content_type: str = Field(max_length=100)
    url: str | None = Field(default=None, max_length=1000)
    storage_key: str | None = Field(default=None, max_length=500)
    caption: str | None = Field(default=None, max_length=300)

    def model_post_init(self, _ctx) -> None:
        if self.content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError(f"content_type must be one of {sorted(ALLOWED_IMAGE_TYPES)}")
        if not (self.url or self.storage_key):
            raise ValueError("an attachment needs a url or a storage_key")
        if self.url and urlparse(self.url).scheme != "https":
            raise ValueError("attachment url must be https")
