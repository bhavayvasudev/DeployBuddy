from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Process liveness only; does not connect to a database or provider."""
    return {"status": "ok", "product": "deploy-buddy"}
