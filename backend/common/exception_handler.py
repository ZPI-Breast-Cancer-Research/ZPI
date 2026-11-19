"""Turns an exception that left a view into the JSON the frontend reads: ``{"code", "detail"}``."""

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

from .errors import SERVER_ERROR, AppError

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    # DRF's own errors first: validation, 404, permissions, wrong method
    response = exception_handler(exc, context)
    if response is not None:
        return response

    request = context.get("request")
    where = f"{request.method} {request.path}" if request is not None else "request"
    set_rollback()
    if isinstance(exc, AppError):
        logger.error("%s: %s: %s", where, type(exc).__name__, exc)
        return Response(exc.payload(), status=exc.status_code)

    # a bug or a failure nobody expected: the traceback goes to the log, not to the client
    logger.exception("%s failed", where)
    return Response(SERVER_ERROR, status=500)
