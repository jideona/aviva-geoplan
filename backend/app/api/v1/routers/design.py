from uuid import UUID

from fastapi import (APIRouter, Body, Depends, File, HTTPException, Response,
                     UploadFile, status)
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.domain.planning.rules import SPLITTER_RATIOS, DesignRules
from app.services import (area_service, design_pack_service, design_service,
                          project_service, scenario_service, schematic_service,
                          word_report_service)
from app.services.area_service import AreaError
from app.services.design_pack_service import DesignPackError
from app.services.design_service import DesignError
from app.services.project_service import ProjectError
from app.services.schematic_service import SchematicError

router = APIRouter(prefix="/projects/{project_id}/design", tags=["design"])


class RunRequest(BaseModel):
    split_stage: str = Field(default="single")           # "single" or "two"
    fdh_split_ratio: int = Field(default=32)
    fat_split_ratio: int = Field(default=1)
    fat_port_count: int = Field(default=16, ge=1, le=64)
    spare_port_ratio: float = Field(default=0.20, ge=0, lt=0.9)
    max_drop_length_m: float = Field(default=150.0, gt=0, le=1000)
    min_premises_per_fat: int = Field(default=4, ge=1)
    assumed_premises_per_building: int = Field(default=1, ge=1)
    max_fat_road_offset_m: float = Field(default=25.0, gt=0)
    # Pilot options: anchor FDH placement to the NOC and tighten the FDH
    # cluster radius so connectorised distribution stays within cable reach.
    noc_anchored: bool = Field(default=False)
    max_fdh_distribution_m: float = Field(default=2000.0, gt=0)


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/rules")
def rules() -> dict:
    d = DesignRules()
    return {
        "splitter_ratios": list(SPLITTER_RATIOS),
        "defaults": {
            "split_stage": d.split_stage,
            "fdh_split_ratio": d.fdh_split_ratio,
            "fat_split_ratio": d.fat_split_ratio,
            "fat_port_count": d.fat_port_count,
            "spare_port_ratio": d.spare_port_ratio,
            "max_drop_length_m": d.max_drop_length_m,
            "assumed_premises_per_building": d.assumed_premises_per_building,
        },
        "splitter_stock": dict(d.stock_map),
        "engine_version": d.engine_version,
    }


@router.post("/run")
def run(project_id: UUID, db: DbSession,
        payload: RunRequest = Body(default=RunRequest()),
        user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    from shapely.geometry import Point
    from shapely.ops import transform as _tf
    from app.domain.crs import STORAGE_EPSG, _transformer
    from app.services.pilot_service import NOC_LON, NOC_LAT

    fields = payload.model_dump()
    anchored = fields.pop("noc_anchored")
    anchor = None
    if anchored:
        to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
        p = _tf(to_metric, Point(NOC_LON, NOC_LAT))
        anchor = (p.x, p.y)
    rules = DesignRules(noc_anchor=anchor, **fields)
    try:
        return design_service.run_design(db, user, project, rules)
    except DesignError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("")
def current(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    design = design_service.current_design(db, project_id)
    return design or {"design_run_id": None, "zones": [], "summary": {},
                      "warnings": [], "rules": {}}


@router.get("/zones.geojson")
def zones_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    return design_service.design_geojson(db, project_id)


@router.get("/drops.geojson")
def drops_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Per-building drop routes (FAT->premises) with measured length and a
    serviceability flag against the design's drop limit."""
    project = _project(db, user, project_id)
    return design_service.drops_geojson(db, project)


@router.get("/pack.xlsx")
def design_pack(project_id: UUID, db: DbSession,
                user=Depends(require(Permission.EXPORT))) -> Response:
    """Network Design Pack — report, Schedule of Materials and priceable BOQ,
    built from the current design, as a single Excel workbook."""
    project = _project(db, user, project_id)
    try:
        pack = design_pack_service.assemble(db, project)
    except DesignPackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    data = design_pack_service.build_workbook(pack)
    name = f"{project.code_prefix.lower()}_network_design_pack.xlsx"
    return Response(content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/pack.docx")
async def design_pack_docx(project_id: UUID, db: DbSession,
                           user=Depends(require(Permission.EXPORT)),
                           aerial: UploadFile | None = File(default=None)) -> Response:
    """Network Design Report — the full design pack as a single Word document:
    summary, methodology, topology + line-schematic diagrams, an aerial
    screenshot of the map (captured client-side and posted here, since a
    faithful render of the live map at whatever zoom/layers were on screen
    can't be reconstructed headlessly), then every schedule from the xlsx
    pack (FDH/FAT schedules, SOM, stock comparison, BOQ, port-level detail,
    ring option) reproduced as Word tables."""
    project = _project(db, user, project_id)
    try:
        pack = design_pack_service.assemble(db, project)
    except DesignPackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc

    aerial_png = await aerial.read() if aerial is not None else None

    topology_png = schematic_png = None
    conn = pack.get("connectivity")
    if conn:
        # A diagram-rendering failure should degrade this section of the
        # report, not fail the whole export — the rest of the pack (summary,
        # methodology, schedules, BOQ) is still valuable on its own.
        try:
            topology_png = word_report_service.svg_to_png_bytes(
                schematic_service.topology_svg(conn))
            schematic_png = word_report_service.svg_to_png_bytes(
                schematic_service.schematic_svg(conn))
        except Exception:                                        # noqa: BLE001
            pass

    data = word_report_service.build_docx(
        pack, aerial_png=aerial_png, topology_png=topology_png,
        schematic_png=schematic_png)
    name = f"{project.code_prefix.lower()}_network_design_report.docx"
    return Response(content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/stock-comparison")
def stock_comparison(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """What the current design needs vs. the organisation's uploaded warehouse
    stock — buildable now vs needs purchase, per SOM line. Upload stock via
    POST /api/v1/inventory/upload. Items with no matching stock data show
    in_stock: null (not 0 — the sheet may simply not carry that item)."""
    project = _project(db, user, project_id)
    try:
        pack = design_pack_service.assemble(db, project)
    except DesignPackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return {"stock_comparison": pack["stock_comparison"], "warnings": pack["warnings"]}


@router.get("/areas.geojson")
def areas_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """N/S/E/W segmentation of the designed area — polygons for the map plus
    per-area FAT/building/premises counts."""
    project = _project(db, user, project_id)
    try:
        return area_service.areas_geojson(db, project)
    except AreaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/area/{quadrant}/pack.xlsx")
def area_pack(project_id: UUID, quadrant: str, db: DbSession,
              user=Depends(require(Permission.EXPORT))) -> Response:
    """Per-area export: summary, scoped measured quantities, priceable BOQ,
    FAT schedule and building connections for one quadrant."""
    project = _project(db, user, project_id)
    try:
        data = area_service.area_pack(db, project, quadrant)
    except AreaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    name = f"{project.code_prefix.lower()}_{quadrant.lower()}_area_pack.xlsx"
    return Response(content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


class DropDeploymentRequest(BaseModel):
    deployment: str | None = Field(default=None)     # 'aerial'|'underground'|None


@router.post("/zones/{zone_code}/drop-deployment")
def set_zone_drop_deployment(
        project_id: UUID, zone_code: str, payload: DropDeploymentRequest,
        db: DbSession, user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Bulk-set the aerial/underground flag for every building in a serving
    zone. Null clears the flag (the project assumption applies again)."""
    project = _project(db, user, project_id)
    try:
        return design_service.set_zone_drop_deployment(
            db, user, project, zone_code, payload.deployment)
    except DesignError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


class AerialShareRequest(BaseModel):
    share: float = Field(ge=0, le=1)


@router.put("/aerial-share")
def set_aerial_share(project_id: UUID, payload: AerialShareRequest,
                     db: DbSession,
                     user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Project assumption: share of UNFLAGGED drops priced as aerial in the
    SOM/BOQ. Explicitly flagged buildings are never subject to it; at 0 every
    unflagged drop prices as underground."""
    project = _project(db, user, project_id)
    project.aerial_drop_share = payload.share
    db.commit()
    return {"aerial_drop_share": float(project.aerial_drop_share)}


class Scenario(RunRequest):
    label: str = ""


class ScenariosRequest(BaseModel):
    scenarios: list[Scenario] = Field(min_length=1, max_length=3)


@router.post("/scenarios")
def scenarios(project_id: UUID, db: DbSession, payload: ScenariosRequest,
              user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Dry-run comparison of up to three rule sets: FAT/FDH counts, trench and
    cable quantities, side by side. The committed design is untouched."""
    project = _project(db, user, project_id)
    try:
        return scenario_service.compare(
            db, project, [s.model_dump() for s in payload.scenarios])
    except scenario_service.ScenarioError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


def _connectivity(db, user, project_id: UUID):
    project = _project(db, user, project_id)
    try:
        return schematic_service.assemble(db, project)
    except SchematicError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/connectivity")
def connectivity(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Port-level connection model: per-FAT port schedule and per-FDH splitter
    tray map, with planning fibre counts."""
    return _connectivity(db, user, project_id)


def _diagram_response(svg: str, fmt: str, name: str) -> Response:
    """Serve a generated diagram as SVG, or convert to PNG/PDF (svglib +
    reportlab — pure Python, no system cairo needed)."""
    if fmt == "svg":
        return Response(content=svg, media_type="image/svg+xml")
    import io
    from reportlab.graphics import renderPDF, renderPM
    from svglib.svglib import svg2rlg
    drawing = svg2rlg(io.StringIO(svg))
    if drawing is None:
        raise HTTPException(status_code=500, detail="Diagram conversion failed.")
    if fmt == "pdf":
        data = renderPDF.drawToString(drawing)
        media = "application/pdf"
    elif fmt == "png":
        data = renderPM.drawToString(drawing, fmt="PNG", dpi=144)
        media = "image/png"
    else:
        raise HTTPException(status_code=400,
                            detail="Format must be svg, png or pdf.")
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition":
                             f'attachment; filename="{name}.{fmt}"'})


@router.get("/topology.{fmt}")
def topology(project_id: UUID, fmt: str, db: DbSession,
             user: CurrentUser) -> Response:
    """Logical topology diagram (NOC → FDH lanes → FAT boxes) as svg/png/pdf."""
    data = _connectivity(db, user, project_id)
    return _diagram_response(schematic_service.topology_svg(data), fmt,
                             "network_topology")


@router.get("/schematic.{fmt}")
def schematic(project_id: UUID, fmt: str, db: DbSession,
              user: CurrentUser) -> Response:
    """Straight-line schematic (SLD) as svg/png/pdf."""
    data = _connectivity(db, user, project_id)
    return _diagram_response(schematic_service.schematic_svg(data), fmt,
                             "network_sld")


@router.get("/staleness")
def staleness(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Whether buildings/corridors changed since the current design ran, so the
    UI can prompt a re-run before the drops/BOQ are trusted."""
    project = _project(db, user, project_id)
    return design_service.design_staleness(db, project)


@router.post("/rerun")
def rerun(project_id: UUID, db: DbSession,
          user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Re-run the current design with its own saved settings."""
    project = _project(db, user, project_id)
    try:
        return design_service.rerun_design(db, user, project)
    except DesignError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
