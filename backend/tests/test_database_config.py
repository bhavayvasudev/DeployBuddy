import pytest

from deploy_buddy.db.config import DatabaseSafetyError, validate_database_url

SAFE = "postgresql+psycopg://deploy_buddy:placeholder@127.0.0.1:55432/deploy_buddy_local"


def test_dedicated_loopback_url_is_allowed():
    assert validate_database_url(SAFE).database == "deploy_buddy_local"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "bad-url",
        "sqlite:///deploy_buddy_local.db",
        SAFE.replace("deploy_buddy_local", "blueprint"),
        SAFE.replace("deploy_buddy_local", "deploy_buddy_local_copy"),
        SAFE.replace("127.0.0.1", "remote.example.com"),
        SAFE.replace("deploy_buddy:placeholder", "postgres:placeholder"),
        SAFE.replace(":placeholder", ""),
        SAFE.replace(":55432", ""),
        SAFE + "?host=remote.example.com",
    ],
)
def test_unsafe_targets_are_rejected_without_disclosing_values(raw):
    with pytest.raises(DatabaseSafetyError) as error:
        validate_database_url(raw)
    assert "placeholder" not in str(error.value)
    assert raw not in str(error.value) if raw else True


def test_bad_port_is_rejected_without_disclosing_password():
    with pytest.raises(DatabaseSafetyError):
        validate_database_url(SAFE.replace(":55432", ":invalid"))
