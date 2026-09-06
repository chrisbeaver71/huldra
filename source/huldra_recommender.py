"""Huldra V1 Profile Recommender.

Derives profile fit from declared profile requirements plus reserved
headroom.  Never infers thresholds from benchmark results or assumes
Chris's 32 GB lab machine.

Supports ~8 GB VRAM / ~16 GB RAM consumers as the minimum viable tier.

Usage::

    from huldra_hardware import detect_hardware
    from huldra_profiles import create_v1_default_catalog
    from huldra_recommender import recommend_profiles

    hw = detect_hardware()
    catalog = create_v1_default_catalog()
    results = recommend_profiles(hw, catalog)
    for r in results:
        print(r.profile.name, r.fit等级)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from huldra_hardware import HardwareProfile
from huldra_profiles import Profile, ProfileCatalog

logger = logging.getLogger(__name__)


class FitLevel(Enum):
    """How well a profile fits the detected hardware."""
    FULL = "full"           # All requirements met with headroom
    PARTIAL = "partial"     # Meets minimum, but below recommended
    INSUFFICIENT = "insufficient"  # Below minimum for one or more requirements
    UNKNOWN = "unknown"     # Cannot determine fit (missing hardware data)


@dataclass
class RequirementCheck:
    """Result of checking one resource requirement."""
    resource: str  # e.g. "vram", "ram", "disk"
    required_gb: float
    available_gb: float
    meets: bool
    margin_gb: float  # available - required (negative = shortfall)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "required_gb": round(self.required_gb, 2),
            "available_gb": round(self.available_gb, 2),
            "meets": self.meets,
            "margin_gb": round(self.margin_gb, 2),
        }


@dataclass
class ProfileRecommendation:
    """Recommendation result for a single profile."""
    profile: Profile
    fit: FitLevel = FitLevel.UNKNOWN
    checks: list[RequirementCheck] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    manual_override_allowed: bool = True

    @property
    def is_usable(self) -> bool:
        return self.fit in (FitLevel.FULL, FitLevel.PARTIAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile.id,
            "profile_name": self.profile.name,
            "fit": self.fit.value,
            "is_usable": self.is_usable,
            "checks": [c.to_dict() for c in self.checks],
            "reasons": self.reasons,
        }


def check_requirements(
    hw: HardwareProfile,
    profile: Profile,
) -> tuple[FitLevel, list[RequirementCheck], list[str]]:
    """Check if hardware meets profile requirements.

    Returns (fit_level, checks, reasons).
    """
    checks: list[RequirementCheck] = []
    reasons: list[str] = []
    res = profile.resources

    # Check VRAM
    if res.min_vram_gb > 0:
        available = hw.usable_vram_gb
        meets = available >= res.min_vram_gb
        margin = available - res.min_vram_gb
        checks.append(RequirementCheck(
            resource="vram",
            required_gb=res.min_vram_gb,
            available_gb=available,
            meets=meets,
            margin_gb=margin,
        ))
        if not meets:
            reasons.append(
                f"VRAM insufficient: {available:.1f} GB available, "
                f"{res.min_vram_gb:.1f} GB required"
            )
    elif hw.gpu.vram_total_gb > 0:
        # GPU exists but no VRAM requirement — still note available
        checks.append(RequirementCheck(
            resource="vram",
            required_gb=0.0,
            available_gb=hw.usable_vram_gb,
            meets=True,
            margin_gb=hw.usable_vram_gb,
        ))

    # Check RAM
    if res.min_ram_gb > 0:
        available = hw.usable_ram_gb
        meets = available >= res.min_ram_gb
        margin = available - res.min_ram_gb
        checks.append(RequirementCheck(
            resource="ram",
            required_gb=res.min_ram_gb,
            available_gb=available,
            meets=meets,
            margin_gb=margin,
        ))
        if not meets:
            reasons.append(
                f"RAM insufficient: {available:.1f} GB available, "
                f"{res.min_ram_gb:.1f} GB required"
            )

    # Check disk
    if res.min_disk_gb > 0:
        available = hw.usable_disk_gb
        meets = available >= res.min_disk_gb
        margin = available - res.min_disk_gb
        checks.append(RequirementCheck(
            resource="disk",
            required_gb=res.min_disk_gb,
            available_gb=available,
            meets=meets,
            margin_gb=margin,
        ))
        if not meets:
            reasons.append(
                f"Disk insufficient: {available:.1f} GB available, "
                f"{res.min_disk_gb:.1f} GB required"
            )

    # Determine fit level
    if not checks:
        fit = FitLevel.UNKNOWN
    elif all(c.meets for c in checks):
        # Check if all also meet recommended
        all_recommended = True
        if res.recommended_vram_gb > 0 and hw.usable_vram_gb < res.recommended_vram_gb:
            all_recommended = False
        if res.recommended_ram_gb > 0 and hw.usable_ram_gb < res.recommended_ram_gb:
            all_recommended = False
        if res.recommended_disk_gb > 0 and hw.usable_disk_gb < res.recommended_disk_gb:
            all_recommended = False

        if all_recommended:
            fit = FitLevel.FULL
            reasons.append("All requirements met with recommended headroom")
        else:
            fit = FitLevel.PARTIAL
            reasons.append("Minimum requirements met, but below recommended")
    else:
        fit = FitLevel.INSUFFICIENT

    return fit, checks, reasons


def recommend_profiles(
    hw: HardwareProfile,
    catalog: ProfileCatalog,
    manual_override: Optional[str] = None,
) -> list[ProfileRecommendation]:
    """Recommend profiles based on hardware and catalog.

    If manual_override is set to a profile ID, that profile is returned
    first with a manual override flag, even if it doesn't fit.

    Results are sorted: FULL > PARTIAL > INSUFFICIENT > UNKNOWN.
    """
    results: list[ProfileRecommendation] = []

    for profile in catalog.profiles:
        fit, checks, reasons = check_requirements(hw, profile)
        rec = ProfileRecommendation(
            profile=profile,
            fit=fit,
            checks=checks,
            reasons=reasons,
            manual_override_allowed=fit != FitLevel.INSUFFICIENT,
        )
        results.append(rec)

    # Sort by fit level
    fit_order = {FitLevel.FULL: 0, FitLevel.PARTIAL: 1, FitLevel.INSUFFICIENT: 2, FitLevel.UNKNOWN: 3}
    results.sort(key=lambda r: (fit_order.get(r.fit, 99), -r.profile.resources.min_vram_gb))

    # Handle manual override
    if manual_override:
        override_profile = catalog.get(manual_override)
        if override_profile:
            # Find existing recommendation or create new one
            existing = next((r for r in results if r.profile.id == manual_override), None)
            if existing:
                if existing.fit == FitLevel.INSUFFICIENT:
                    existing.reasons.append(
                        f"MANUAL OVERRIDE: Profile '{manual_override}' does not meet "
                        f"hardware requirements. Use with caution."
                    )
                    existing.manual_override_allowed = True
                # Move to front
                results.remove(existing)
                results.insert(0, existing)
            else:
                fit, checks, reasons = check_requirements(hw, override_profile)
                reasons.append(f"MANUAL OVERRIDE requested for '{manual_override}'")
                rec = ProfileRecommendation(
                    profile=override_profile,
                    fit=fit,
                    checks=checks,
                    reasons=reasons,
                    manual_override_allowed=True,
                )
                results.insert(0, rec)
        else:
            logger.warning(
                "Manual override profile '%s' not found in catalog", manual_override
            )

    return results


def get_best_profile(
    hw: HardwareProfile,
    catalog: ProfileCatalog,
    manual_override: Optional[str] = None,
) -> Optional[ProfileRecommendation]:
    """Get the single best profile recommendation."""
    results = recommend_profiles(hw, catalog, manual_override)
    for rec in results:
        if rec.is_usable:
            return rec
    return results[0] if results else None


def format_recommendation_report(
    hw: HardwareProfile,
    results: list[ProfileRecommendation],
) -> str:
    """Format a human-readable recommendation report."""
    lines = [
        "=== Huldra V1 Profile Recommendation ===",
        "",
        "Hardware:",
        f"  GPU: {hw.gpu.name} ({hw.gpu.vram_total_gb:.1f} GB VRAM, vendor={hw.gpu.vendor})",
        f"  RAM: {hw.ram_total_gb:.1f} GB total, {hw.ram_available_gb:.1f} GB available",
        f"  Disk: {hw.storage.free_gb:.1f} GB free at {hw.storage.path}",
        f"  OS: {hw.os_name} {hw.os_version}",
        f"  Usable VRAM: {hw.usable_vram_gb:.1f} GB, Usable RAM: {hw.usable_ram_gb:.1f} GB",
        "",
        "Profiles:",
    ]

    for rec in results:
        marker = ">>>" if rec.fit in (FitLevel.FULL, FitLevel.PARTIAL) else "   "
        lines.append(
            f"  {marker} [{rec.fit.value.upper():>13}] {rec.profile.name}"
        )
        for check in rec.checks:
            status = "OK" if check.meets else "FAIL"
            lines.append(
                f"         {check.resource}: {check.available_gb:.1f}/{check.required_gb:.1f} GB [{status}]"
            )
        for reason in rec.reasons:
            lines.append(f"         {reason}")
        lines.append("")

    return "\n".join(lines)
