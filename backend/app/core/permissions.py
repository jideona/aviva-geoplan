"""Role and permission model (SRD Section 11).

Permissions are checked server-side on every route. The frontend uses the same
names only to decide what to display.
"""
from enum import Enum


class Role(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    ORG_ADMIN = "org_admin"
    PROJECT_MANAGER = "project_manager"
    GIS_PLANNER = "gis_planner"
    NETWORK_DESIGNER = "network_designer"
    SURVEY_COORDINATOR = "survey_coordinator"
    FIELD_SURVEYOR = "field_surveyor"
    SALES_SURVEYOR = "sales_surveyor"
    QA_REVIEWER = "qa_reviewer"
    CONSTRUCTION_MANAGER = "construction_manager"
    CONTRACTOR = "contractor"
    VIEWER = "viewer"
    CLIENT_REVIEWER = "client_reviewer"


class Permission(str, Enum):
    PROJECT_CREATE = "project:create"
    PROJECT_EDIT = "project:edit"
    PROJECT_VIEW = "project:view"
    GIS_IMPORT = "gis:import"
    GIS_EDIT = "gis:edit"
    BUILDING_EDIT = "building:edit"
    # Narrower than BUILDING_EDIT: lets a field role update a building's own
    # surveyed attributes (type, units, address, notes) and flag a footprint
    # as not existing from the survey app, without granting the desktop
    # capabilities BUILDING_EDIT also covers (drawing/moving/deleting
    # arbitrary footprints). Every role holding BUILDING_EDIT is granted this
    # too, so nothing that could edit a building before loses mobile access.
    BUILDING_FIELD_UPDATE = "building:field_update"
    EXPORT = "export"
    AUDIT_VIEW = "audit:view"
    USER_MANAGE = "user:manage"
    INVENTORY_MANAGE = "inventory:manage"
    # Mobile field-survey permissions (SRD Section 11 amendment, survey
    # phase). Distinct from BUILDING_FIELD_UPDATE: these gate *visibility*
    # and *capture ability* on the mobile app, not desktop building edits.
    # FIELD_DATA_VIEW's "see everyone's project field work" scope is a base
    # field-role capability, never admin-gated — shared awareness across
    # surveyors is the point, not a privilege.
    FIELD_CAPTURE = "field:capture"
    FIELD_DATA_VIEW = "field_data:view"
    FIELD_ACTIVITY_VIEW = "field_activity:view"
    QA_REVIEW = "qa:review"
    # Full task CRUD + reassignment. Updating status/updates/issues on a task
    # you're personally assigned to is allowed without this permission —
    # enforced in deployment_service, not here, since it depends on the row.
    TASK_MANAGE = "task:manage"


_ALL = set(Permission)

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.PLATFORM_ADMIN: _ALL,
    Role.ORG_ADMIN: _ALL,
    Role.PROJECT_MANAGER: {
        Permission.PROJECT_CREATE, Permission.PROJECT_EDIT, Permission.PROJECT_VIEW,
        Permission.GIS_IMPORT, Permission.GIS_EDIT, Permission.BUILDING_EDIT,
        Permission.BUILDING_FIELD_UPDATE,
        Permission.EXPORT, Permission.AUDIT_VIEW, Permission.INVENTORY_MANAGE,
        Permission.TASK_MANAGE, Permission.USER_MANAGE,
        Permission.FIELD_CAPTURE, Permission.FIELD_DATA_VIEW,
        Permission.FIELD_ACTIVITY_VIEW, Permission.QA_REVIEW,
    },
    Role.GIS_PLANNER: {
        Permission.PROJECT_VIEW, Permission.GIS_IMPORT, Permission.GIS_EDIT,
        Permission.BUILDING_EDIT, Permission.BUILDING_FIELD_UPDATE, Permission.EXPORT,
    },
    Role.NETWORK_DESIGNER: {
        Permission.PROJECT_VIEW, Permission.GIS_EDIT, Permission.EXPORT,
        Permission.INVENTORY_MANAGE,
    },
    Role.SURVEY_COORDINATOR: {Permission.PROJECT_VIEW, Permission.BUILDING_EDIT,
                              Permission.BUILDING_FIELD_UPDATE, Permission.TASK_MANAGE,
                              Permission.FIELD_DATA_VIEW, Permission.FIELD_ACTIVITY_VIEW},
    Role.FIELD_SURVEYOR: {Permission.PROJECT_VIEW, Permission.BUILDING_FIELD_UPDATE,
                          Permission.FIELD_CAPTURE, Permission.FIELD_DATA_VIEW,
                          Permission.FIELD_ACTIVITY_VIEW},
    Role.SALES_SURVEYOR: {Permission.PROJECT_VIEW, Permission.BUILDING_FIELD_UPDATE,
                          Permission.FIELD_CAPTURE, Permission.FIELD_DATA_VIEW,
                          Permission.FIELD_ACTIVITY_VIEW},
    Role.QA_REVIEWER: {Permission.PROJECT_VIEW, Permission.BUILDING_EDIT,
                       Permission.BUILDING_FIELD_UPDATE, Permission.AUDIT_VIEW,
                       Permission.FIELD_DATA_VIEW, Permission.FIELD_ACTIVITY_VIEW,
                       Permission.QA_REVIEW},
    Role.CONSTRUCTION_MANAGER: {Permission.PROJECT_VIEW, Permission.EXPORT,
                                Permission.TASK_MANAGE},
    Role.CONTRACTOR: {Permission.PROJECT_VIEW},
    Role.VIEWER: {Permission.PROJECT_VIEW, Permission.EXPORT},
    Role.CLIENT_REVIEWER: {Permission.PROJECT_VIEW},
}


def permissions_for(roles: list[str]) -> set[Permission]:
    out: set[Permission] = set()
    for r in roles:
        try:
            out |= ROLE_PERMISSIONS[Role(r)]
        except ValueError:
            continue
    return out


def has_permission(roles: list[str], perm: Permission) -> bool:
    return perm in permissions_for(roles)
