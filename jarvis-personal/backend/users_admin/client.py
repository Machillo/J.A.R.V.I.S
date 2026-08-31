from backend.auth.saas import get_managed_user, grant_courtesy, list_managed_users, revoke_courtesy


def list_users(search: str | None = None):
    return list_managed_users(search)


def get_user(account_id: str):
    return get_managed_user(account_id)


def grant_user_courtesy(account_id: str, plan: str, days: int, note: str | None = None):
    return grant_courtesy(account_id, plan, days, note)


def revoke_user_courtesy(account_id: str):
    return revoke_courtesy(account_id)
