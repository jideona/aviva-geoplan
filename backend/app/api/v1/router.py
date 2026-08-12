from fastapi import APIRouter

from app.api.v1.routers import (assignment, auth, boundaries,
                                building_edit, connectorised,
                                corridor, coverage,
                                deployment, design, features,
                                field_data, health, imports, inventory, naming,
                                parcels,
                                facility_edit, mobile, optical, pilot, projects,
                                readiness, register, routing,
                                street_edit, walkthrough)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(boundaries.router)
api_router.include_router(imports.router)
api_router.include_router(features.router)
api_router.include_router(assignment.router)
api_router.include_router(naming.router)
api_router.include_router(register.router)
api_router.include_router(readiness.router)
api_router.include_router(walkthrough.router)
api_router.include_router(field_data.router)
api_router.include_router(design.router)
api_router.include_router(parcels.router)
api_router.include_router(coverage.router)
api_router.include_router(connectorised.router)
api_router.include_router(pilot.router)
api_router.include_router(routing.router)
api_router.include_router(optical.router)
api_router.include_router(building_edit.router)
api_router.include_router(facility_edit.router)
api_router.include_router(corridor.router)
api_router.include_router(mobile.router)
api_router.include_router(street_edit.router)
api_router.include_router(inventory.router)
api_router.include_router(deployment.router)
