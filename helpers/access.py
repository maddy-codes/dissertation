"""Tenant access control for the restricted 'client' user role."""
from __future__ import annotations

from setup.models import ClientAccess


def user_can_view_tenant(user, tenant_id: str) -> bool:
    """Whether `user` may view/act on `tenant_id`.

    Staff/partner behavior is unchanged: they're trusted based on their own
    Xero OAuth connection scope, as today. Only the restricted 'client' role
    is gated by an explicit ClientAccess grant.
    """
    if user.role == 'client':
        return (
            ClientAccess.query.filter_by(user_id=user.id, tenant_id=tenant_id).first()
            is not None
        )
    return True
