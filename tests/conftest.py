import pytest


@pytest.fixture(autouse=True)
def stub_remote_translation_spec_fetch(monkeypatch):
    def fail_fetch(url: str) -> dict:
        raise ValueError(
            f"Failed to fetch OpenAPI spec from {url}: network access disabled in tests"
        )

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", fail_fetch)
