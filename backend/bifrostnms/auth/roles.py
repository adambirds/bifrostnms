from enum import StrEnum


class RealmRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class RealmPermission(StrEnum):
    REALM_READ = "realm.read"
    REALM_MANAGE = "realm.manage"
    REALM_DELETE = "realm.delete"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    MONITORING_READ = "monitoring.read"
    MONITORING_MANAGE = "monitoring.manage"
    AGENT_CREDENTIALS_MANAGE = "agent_credentials.manage"
    ALERTS_ACKNOWLEDGE = "alerts.acknowledge"


ROLE_PERMISSIONS: dict[RealmRole, frozenset[RealmPermission]] = {
    RealmRole.OWNER: frozenset(RealmPermission),
    RealmRole.ADMIN: frozenset(
        {
            RealmPermission.REALM_READ,
            RealmPermission.MEMBERS_READ,
            RealmPermission.MEMBERS_MANAGE,
            RealmPermission.MONITORING_READ,
            RealmPermission.MONITORING_MANAGE,
            RealmPermission.AGENT_CREDENTIALS_MANAGE,
            RealmPermission.ALERTS_ACKNOWLEDGE,
        }
    ),
    RealmRole.MEMBER: frozenset(
        {
            RealmPermission.REALM_READ,
            RealmPermission.MONITORING_READ,
            RealmPermission.MONITORING_MANAGE,
            RealmPermission.ALERTS_ACKNOWLEDGE,
        }
    ),
    RealmRole.VIEWER: frozenset(
        {
            RealmPermission.REALM_READ,
            RealmPermission.MONITORING_READ,
        }
    ),
}


def role_has_permission(role: RealmRole, permission: RealmPermission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
