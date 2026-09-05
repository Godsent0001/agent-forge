from fastapi import APIRouter

from app.tools.catalog import CATALOG, SHELVES, catalog_by_shelf

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
def list_catalog():
    """Flat list — id (kind), name, shelf, description, status."""
    return [
        {"kind": e.kind, "name": e.name, "shelf": e.shelf, "description": e.description, "status": e.status}
        for e in CATALOG
    ]


@router.get("/shelves")
def list_shelves():
    """Grouped by shelf, in shelf display order, for the picker UI."""
    grouped = catalog_by_shelf()
    return [
        {
            "shelf": shelf_id,
            "label": SHELVES[shelf_id],
            "tools": [
                {"kind": e.kind, "name": e.name, "description": e.description, "status": e.status}
                for e in entries
            ],
        }
        for shelf_id, entries in grouped.items()
        if entries
    ]
