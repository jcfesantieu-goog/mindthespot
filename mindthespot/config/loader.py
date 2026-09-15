"""Config loader for MindTheSpot catalog and watchlists."""

import logging
from pathlib import Path

import yaml

from mindthespot.config.models import (
    CatalogConfig,
    InstancePoolTarget,
    WatchlistConfig,
)

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "default_catalog.yaml"


def extract_family_from_machine_type(machine_type: str) -> str:
    """Extract family prefix from machine type string (e.g., 'c4d-standard-8' -> 'c4d')."""
    cleaned = machine_type.strip().lower()
    parts = cleaned.split("-")
    return parts[0] if parts else cleaned


def load_catalog(path: str | Path | None = None) -> CatalogConfig:
    """Load and validate default catalog YAML file."""
    catalog_path = Path(path) if path else DEFAULT_CATALOG_PATH
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog file not found: {catalog_path}")

    with open(catalog_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return CatalogConfig.model_validate(data)


def load_watchlist(path: str | Path | None = None) -> WatchlistConfig:
    """Load and validate custom watchlist YAML file.

    If file path does not exist, returns an empty WatchlistConfig.
    """
    if not path:
        return WatchlistConfig(watchlist=[])

    watchlist_path = Path(path)
    if not watchlist_path.exists():
        logger.warning("Watchlist file '%s' does not exist; proceeding with empty watchlist.", watchlist_path)
        return WatchlistConfig(watchlist=[])

    with open(watchlist_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "watchlist" not in data:
        return WatchlistConfig(watchlist=[])

    return WatchlistConfig.model_validate(data)


def resolve_targets(
    catalog: CatalogConfig,
    watchlist: WatchlistConfig | None = None,
) -> list[InstancePoolTarget]:
    """Resolve and deduplicate full target instance pools from catalog and watchlist.

    Watchlist entries that overlap with default catalog targets will mark those targets
    as `is_watchlist = True` with any custom label. Watchlist entries for additional
    pools will be appended to the target list.
    """
    targets_map: dict[str, InstancePoolTarget] = {}

    # 1. Expand standard catalog
    for region_cfg in catalog.regions:
        for family_cfg in catalog.families:
            for zone in region_cfg.zones:
                for machine_type in family_cfg.machine_types:
                    key = f"{region_cfg.region}/{zone}/{machine_type}"
                    targets_map[key] = InstancePoolTarget(
                        region=region_cfg.region,
                        zone=zone,
                        machine_type=machine_type,
                        family=family_cfg.family,
                        is_watchlist=False,
                    )

    # 2. Expand and merge custom watchlist
    if watchlist and watchlist.watchlist:
        known_region_zones = {r.region: r.zones for r in catalog.regions}

        for entry in watchlist.watchlist:
            region = entry.region.strip().lower()
            zones = entry.zones
            # If zones are not specified or empty, expand to all known zones in this region
            if not zones:
                zones = known_region_zones.get(region, [])
                if not zones:
                    logger.warning("No zones known for watchlist region '%s'; skipping entry %s", region, entry.name)
                    continue

            for zone in zones:
                zone_clean = zone.strip().lower()
                for machine_type in entry.machine_types:
                    mt_clean = machine_type.strip().lower()
                    key = f"{region}/{zone_clean}/{mt_clean}"
                    family = extract_family_from_machine_type(mt_clean)

                    if key in targets_map:
                        targets_map[key].is_watchlist = True
                        if entry.name:
                            targets_map[key].custom_label = entry.name
                    else:
                        targets_map[key] = InstancePoolTarget(
                            region=region,
                            zone=zone_clean,
                            machine_type=mt_clean,
                            family=family,
                            is_watchlist=True,
                            custom_label=entry.name,
                        )

    return list(targets_map.values())
