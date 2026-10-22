from __future__ import annotations

import logging

import structlog

QUIET_LIBRARIES = ("boto3", "botocore", "s3transfer", "urllib3")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    # Client libraries log request details at DEBUG (botocore includes the signing credential's access key ID).
    # Application DEBUG logging must never switch that on.
    for noisy in QUIET_LIBRARIES:
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
    )
