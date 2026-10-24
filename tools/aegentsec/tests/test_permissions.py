from aegentsec.services import has_permission

CATALOGUE = {"inventory:read", "purchase:create"}


def test_permissions_are_exact_and_deny_by_default():
    assert has_permission({"inventory:read"}, "inventory:read", CATALOGUE)
    assert not has_permission({"inventory:read"}, "purchase:create", CATALOGUE)
    assert not has_permission(set(), "inventory:read", CATALOGUE)
    assert not has_permission({"inventory:*"}, "inventory:read", CATALOGUE)
    assert not has_permission({"unknown:read"}, "unknown:read", CATALOGUE)
    assert not has_permission({"inventory:read"}, "inventory:read", set())
