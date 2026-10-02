import pytest


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    """Keep every test away from the real %APPDATA%/OpenRA-AI settings, provider key and install token.

    Tests that exercise the data-root rules may still set APPDATA or OPENRA_AI_DATA_DIR themselves.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("OPENRA_AI_DATA_DIR", raising=False)
