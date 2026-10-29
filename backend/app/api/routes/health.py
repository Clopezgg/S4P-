import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.integrations.azure_blob import evidence_storage_is_reachable

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/api/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
@router.get("/api/readyz", include_in_schema=False)
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as error:  # pragma: no cover - depende de infraestructura real
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible",
        ) from error

    settings = get_settings()
    if settings.evidence_backend != "none":
        ok, detail = evidence_storage_is_reachable(settings)
        if not ok:
            # No se reporta healthy si el almacenamiento de evidencias esta
            # configurado pero la Managed Identity no puede alcanzarlo. El
            # detalle es solo el tipo de excepcion, nunca URL/credencial.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Almacenamiento de evidencias no disponible ({detail or 'desconocido'})",
            )

    return {"status": "ok"}


@router.get("/backupz")
@router.get("/api/backupz", include_in_schema=False)
def backupz() -> dict[str, str]:
    """Safe read-only backup freshness signal for external monitoring.

    No archive metadata, object paths or credentials are exposed. Keep this
    separate from /readyz: a backup outage must not trigger an application
    restart loop or lock out access to the ERP.
    """
    if os.environ.get("S4P_BACKUP_SCHEDULE_ENABLED") != "1":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Respaldo externo no configurado",
        )

    try:
        from app.services.backup_worker import _bridge, _json_call

        latest = _json_call(_bridge(), "status")
        if latest.get("available") is not True:
            raise ValueError("No backup manifest")
        timestamp = latest.get("createdAt")
        if not isinstance(timestamp, str):
            raise ValueError("Backup timestamp unavailable")
        created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if not 0 <= age <= 36 * 3600:
            raise ValueError("Backup is stale or dated in the future")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Respaldo externo sin verificación reciente",
        ) from exc
    return {"status": "ok"}


@router.get("/version")
@router.get("/api/version", include_in_schema=False)
def version() -> dict[str, str]:
    settings = get_settings()
    return {
        "gitSha": settings.git_sha,
        "buildTime": settings.build_time,
        "environment": settings.app_env,
    }
