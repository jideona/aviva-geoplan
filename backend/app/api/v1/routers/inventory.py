from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import inventory_service
from app.services.inventory_service import InventoryError

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/upload")
async def upload_stock(
    db: DbSession,
    file: UploadFile = File(...),
    user=Depends(require(Permission.INVENTORY_MANAGE)),
) -> dict:
    """Replace the organisation's warehouse stock snapshot from a CSV/XLSX
    sheet (any layout close to the Aviva Asset Register template — headers are
    matched case-insensitively with common aliases). This REPLACES the
    previous snapshot wholesale; it is a point-in-time picture, not a ledger.
    """
    data = await file.read()
    try:
        result = inventory_service.replace_stock(
            db, user.organisation_id, file.filename or "stock.csv", data)
    except InventoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return result.as_dict()


@router.get("")
def list_stock(db: DbSession, user: CurrentUser) -> dict:
    """Current stock snapshot for the caller's organisation."""
    items = inventory_service.list_stock(db, user.organisation_id)
    return {"count": len(items), "items": [{
        "id": str(i.id), "stock_code": i.stock_code, "category": i.category,
        "subcategory": i.subcategory, "manufacturer": i.manufacturer,
        "product_name": i.product_name, "model": i.model,
        "quantity": float(i.quantity), "uom": i.uom,
        "match_key": i.match_key, "unit_cost": (float(i.unit_cost)
                                                 if i.unit_cost is not None else None),
        "condition": i.condition, "warehouse": i.warehouse,
        "source_filename": i.source_filename, "remarks": i.remarks,
    } for i in items]}
