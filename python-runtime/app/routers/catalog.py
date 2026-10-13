from typing import Literal

from fastapi import APIRouter, Query

from app.tools.catalog import CATALOG, SHELVES, catalog_by_shelf

router = APIRouter(prefix="/catalog", tags=["catalog"])
PackFilter = Literal["video", "none"]


def _entries(pack: PackFilter | None):
    if pack == "video":
        return [entry for entry in CATALOG if entry.pack == "video"]
    if pack == "none":
        return [entry for entry in CATALOG if entry.pack is None]
    return CATALOG


@router.get("")
def list_catalog(pack: PackFilter | None = Query(default=None)):
    """Flat catalog. Use pack=video or pack=none to filter pack membership."""
    return [
        {"kind": entry.kind, "name": entry.name, "shelf": entry.shelf,
         "description": entry.description, "status": entry.status, "pack": entry.pack}
        for entry in _entries(pack)
    ]


@router.get("/shelves")
def list_shelves(pack: PackFilter | None = Query(default=None)):
    """Grouped catalog; the optional video pack can be enabled independently."""
    grouped = catalog_by_shelf(_entries(pack))
    return [
        {
            "shelf": shelf_id,
            "label": SHELVES[shelf_id],
            "tools": [
                {"kind": entry.kind, "name": entry.name, "description": entry.description,
                 "status": entry.status, "pack": entry.pack}
                for entry in entries
            ],
        }
        for shelf_id, entries in grouped.items()
        if entries
    ]
