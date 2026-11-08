"""Reviewed container identities, separate from application dependency policy.

Recipes pin multi-platform indexes. Child/config identities qualify only the
linux/amd64 evidence; an index pin is not ARM64 execution evidence.
"""

from dataclasses import dataclass
from types import MappingProxyType

BASE_REFERENCE_POLICY_ID = "ef-v5-noble-1"
HISTORICAL_BASE_REFERENCE_POLICY_ID = "ef-v5-images-2026-10-17"


@dataclass(frozen=True)
class ContainerBase:
    tag: str
    index_digest: str
    amd64_manifest_digest: str
    config_digest: str

    @property
    def reference(self) -> str:
        return f"{self.tag}@{self.index_digest}"


CONTAINER_BASES = MappingProxyType({
    "17": (
        ContainerBase(
            "maven:3.9.16-eclipse-temurin-17-noble",
            "sha256:1a352420f7aba21f5ad08df31bab55f74c013fb491f1ae8ab1dd7ff9ed698584",
            "sha256:c97d0fa42bed8c381518d76d7ca541ff5c6427b21fa93ac6fc4bd68ffb9a258d",
            "sha256:caa1c99435b94bae143279df3c73652ef32fb1bae6a4f21ea544da05c85c16ee",
        ),
        ContainerBase(
            "eclipse-temurin:17.0.20.1_1-jre-noble",
            "sha256:07fa0356cf354c5252947575f42ed42aa6fd921f36438b7bc77ad81c31c537dd",
            "sha256:e7ee15413d334217ca732978500b310e1a0bb8a5e54d9b6dd12509f636cda99e",
            "sha256:5eb339fa0dc333ecdb302fbacc8292df0d5bb12b13b22c74a493b0ff2b476852",
        ),
    ),
    "21": (
        ContainerBase(
            "maven:3.9.16-eclipse-temurin-21-noble",
            "sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320",
            "sha256:80034909d9a9f0b89d3d2c583f07f3b7650309bc4e6b886ad5b860b9e1bfa439",
            "sha256:be15c983f424d4cc583651a8af84fb8acc43c96a8306b7e8f8a8e93d5d93f7fb",
        ),
        ContainerBase(
            "eclipse-temurin:21.0.12.1_1-jre-noble",
            "sha256:35501d3f93173b420ac9001658eb68157e813316b865087e345c187fca422c4c",
            "sha256:da0f0d242bec39e3fe5c1ac4c415840f03be9cef848c243d723166708e02148c",
            "sha256:1adc899ed973c648859da2577005db5cb567a91291744db96a96ff3421b3bf5a",
        ),
    ),
})

BASE_REFERENCE_POLICIES = MappingProxyType({
    HISTORICAL_BASE_REFERENCE_POLICY_ID: MappingProxyType({
        java: (f"maven:3.9.9-eclipse-temurin-{java}", f"eclipse-temurin:{java}-jre")
        for java in ("17", "21")
    }),
    BASE_REFERENCE_POLICY_ID: MappingProxyType({
        java: tuple(base.reference for base in pair) for java, pair in CONTAINER_BASES.items()
    }),
})


def base_references(java: str | int, policy: str = BASE_REFERENCE_POLICY_ID) -> tuple[str, str]:
    try:
        return BASE_REFERENCE_POLICIES[policy][str(java)]
    except KeyError as exc:
        raise ValueError("Unsupported container reference policy or Java baseline") from exc


def declared_base_references(row: dict) -> tuple[str, str]:
    """Old declarations retain their exact historical contract, not a wildcard."""
    java = "21" if row["case"].endswith("j21") else "17"
    actual = (row.get("build_base"), row.get("runtime_base"))
    policy = row.get("base_reference_policy")
    if policy is None:
        if actual == (None, None):
            return base_references(java, HISTORICAL_BASE_REFERENCE_POLICY_ID)
        policy = next((key for key in BASE_REFERENCE_POLICIES
                       if actual == base_references(java, key)), None)
    expected = base_references(java, policy)
    if actual != expected:
        raise ValueError("Declared bases differ from the reviewed reference policy")
    return expected


def pinned_base(reference: str) -> ContainerBase | None:
    return next((base for pair in CONTAINER_BASES.values() for base in pair
                 if base.reference == reference), None)


def reference_sets() -> tuple[frozenset[str], ...]:
    return tuple(frozenset(ref for pair in mapping.values() for ref in pair)
                 for mapping in BASE_REFERENCE_POLICIES.values())
