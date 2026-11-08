"""Explicit framework type selection for the opt-in Kafka preview."""

from appbuilder.target_profiles.catalog import TARGET_PROFILES


def is_boot41(profile_name: str) -> bool:
    profile = TARGET_PROFILES.get(profile_name)
    return profile is not None and profile.experimental_boot41


def jackson_import(profile_name: str, suffix: str) -> str:
    package = "tools.jackson" if is_boot41(profile_name) else "com.fasterxml.jackson"
    return f"{package}.{suffix}"
