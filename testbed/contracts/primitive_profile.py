"""Primitive profile and version contract shared by builders and rollout."""

from __future__ import annotations

PRIMITIVE_PROFILE_CONTRACT_VERSION = "v2_4_5_primitive_profile_v1"

PRIMITIVE_NAMES_4P = ("dig", "carry", "dump", "return")
PRIMITIVE_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")
PRIMITIVE_NAMES = PRIMITIVE_NAMES_4P

PRIMITIVE_VERSION_V2_2_4P = "v2_2_4primitives"
PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass_4primitives"
PRIMITIVE_VERSION_V2_2_5P = "v2_2_5primitives"
PRIMITIVE_VERSION = PRIMITIVE_VERSION_V2_2_4P
PRIMITIVE_VERSION_5P = PRIMITIVE_VERSION_V2_2_5P

PRIMITIVE_BOUNDARY_PROFILE_DEFAULT = "v2_2_middle_handoff"
PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK = "v2_2_effect_release_fallback"
PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass"
PRIMITIVE_BOUNDARY_PROFILES = (
    PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)

CYCLE_BOUNDARY_PROFILE_LEGACY = "legacy"
CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass"
CYCLE_BOUNDARY_PROFILES = (
    CYCLE_BOUNDARY_PROFILE_LEGACY,
    CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)


def normalize_primitive_boundary_profile(profile: str | None) -> str:
    """Normalize primitive builder profile config with legacy error behavior."""
    if profile in (None, ""):
        return PRIMITIVE_BOUNDARY_PROFILE_DEFAULT
    value = str(profile).strip()
    if value not in PRIMITIVE_BOUNDARY_PROFILES:
        raise ValueError(
            f"Unsupported V2.2 primitive boundary profile {profile!r}. "
            f"Expected one of {', '.join(PRIMITIVE_BOUNDARY_PROFILES)}."
        )
    return value


def primitive_version_for_boundary_profile(profile: str | None) -> str:
    """Return the primitive dataset version implied by a boundary profile."""
    value = normalize_primitive_boundary_profile(profile)
    if value == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS:
        return PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS
    return PRIMITIVE_VERSION


def is_v2_4_5_spatial_mass_profile(profile: str | None) -> bool:
    """Return true when a primitive boundary profile is the current 2.4.5 mainline."""
    return (
        normalize_primitive_boundary_profile(profile)
        == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )


def normalize_cycle_boundary_profile(profile: str) -> str:
    """Validate online cycle boundary detector profile names."""
    value = str(profile)
    if value not in CYCLE_BOUNDARY_PROFILES:
        raise ValueError(
            f"Unsupported cycle boundary_profile {profile!r}; expected one of "
            f"{sorted(CYCLE_BOUNDARY_PROFILES)}."
        )
    return value
