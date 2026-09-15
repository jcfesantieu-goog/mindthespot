"""Tests for MindTheSpot configuration models and loader."""

import pytest
from pydantic import ValidationError

from mindthespot.config.loader import (
    DEFAULT_CATALOG_PATH,
    extract_family_from_machine_type,
    load_catalog,
    load_watchlist,
    resolve_targets,
)
from mindthespot.config.models import (
    CatalogConfig,
    MachineFamilyConfig,
    RegionConfig,
    WatchlistConfig,
    WatchlistEntry,
)


def test_extract_family_from_machine_type():
    assert extract_family_from_machine_type("c4d-standard-8") == "c4d"
    assert extract_family_from_machine_type("c3d-standard-16") == "c3d"
    assert extract_family_from_machine_type("c4a-standard-4") == "c4a"
    assert extract_family_from_machine_type("n2d-highmem-4") == "n2d"
    assert extract_family_from_machine_type("e2-micro") == "e2"


def test_default_catalog_loads_and_contains_required_families():
    assert DEFAULT_CATALOG_PATH.exists()
    catalog = load_catalog(DEFAULT_CATALOG_PATH)

    assert catalog.version == "1.0"
    assert len(catalog.regions) == 43
    assert len(catalog.families) == 11

    # Verify key instance families from requirements
    family_names = {f.family for f in catalog.families}
    assert "c4d" in family_names
    assert "c3d" in family_names
    assert "c4a" in family_names
    assert "c3" in family_names
    assert "c2" in family_names
    assert "n4" in family_names
    assert "n2d" in family_names
    assert "n2" in family_names
    assert "t2d" in family_names
    assert "t2a" in family_names
    assert "e2" in family_names

    # Verify equivalent families mapping exists
    c4d = catalog.get_family("c4d")
    assert c4d is not None
    assert "c3d" in c4d.equivalent_families
    assert "c4a" in c4d.equivalent_families


def test_region_config_zone_prefix_validation():
    # Valid region and zones
    valid_region = RegionConfig(
        region="europe-west4",
        zones=["europe-west4-a", "europe-west4-b"],
    )
    assert valid_region.region == "europe-west4"
    assert len(valid_region.zones) == 2

    # Invalid zone prefix should raise validation error
    with pytest.raises(ValidationError) as exc_info:
        RegionConfig(
            region="europe-west4",
            zones=["us-central1-a"],
        )
    assert "must start with region" in str(exc_info.value)


def test_load_watchlist_example(tmp_path):
    watchlist_path = DEFAULT_CATALOG_PATH.parent / "watchlist.example.yaml"
    assert watchlist_path.exists()
    wl = load_watchlist(watchlist_path)

    assert len(wl.watchlist) >= 2
    entry = wl.watchlist[0]
    assert entry.region == "europe-west4"
    assert "c4d-standard-16" in entry.machine_types
    assert entry.alert_threshold_z == 2.2


def test_load_watchlist_non_existent():
    wl = load_watchlist("/tmp/non_existent_watchlist_file.yaml")
    assert isinstance(wl, WatchlistConfig)
    assert len(wl.watchlist) == 0


def test_resolve_targets_catalog_only():
    catalog = CatalogConfig(
        regions=[
            RegionConfig(region="europe-west4", zones=["europe-west4-a", "europe-west4-b"]),
        ],
        families=[
            MachineFamilyConfig(
                family="c4d",
                machine_types=["c4d-standard-4", "c4d-standard-8"],
                equivalent_families=["c3d"],
            ),
        ],
    )

    targets = resolve_targets(catalog, None)
    # 1 region * 2 zones * 2 machine_types = 4 targets
    assert len(targets) == 4
    for t in targets:
        assert t.is_watchlist is False
        assert t.family == "c4d"
        assert t.region == "europe-west4"


def test_resolve_targets_merges_watchlist_and_expands_empty_zones():
    catalog = CatalogConfig(
        regions=[
            RegionConfig(
                region="europe-west4",
                zones=["europe-west4-a", "europe-west4-b"],
            ),
            RegionConfig(
                region="europe-west9",
                zones=["europe-west9-a", "europe-west9-b", "europe-west9-c"],
            ),
        ],
        families=[
            MachineFamilyConfig(
                family="c4d",
                machine_types=["c4d-standard-4"],
                equivalent_families=["c3d"],
            ),
        ],
    )

    watchlist = WatchlistConfig(
        watchlist=[
            # Overlap with existing catalog target
            WatchlistEntry(
                name="Overlap Target",
                region="europe-west4",
                zones=["europe-west4-a"],
                machine_types=["c4d-standard-4"],
            ),
            # Empty zones should expand to all 3 zones in europe-west9
            WatchlistEntry(
                name="All Paris Zones",
                region="europe-west9",
                zones=[],
                machine_types=["c3d-standard-8"],
            ),
        ]
    )

    targets = resolve_targets(catalog, watchlist)
    by_key = {t.pool_key: t for t in targets}

    # Verify overlapping target marked as watchlist
    overlap = by_key["europe-west4/europe-west4-a/c4d-standard-4"]
    assert overlap.is_watchlist is True
    assert overlap.custom_label == "Overlap Target"

    # Verify non-overlapping target remains is_watchlist=False
    non_overlap = by_key["europe-west4/europe-west4-b/c4d-standard-4"]
    assert non_overlap.is_watchlist is False

    # Verify expansion of all 3 zones for europe-west9
    assert "europe-west9/europe-west9-a/c3d-standard-8" in by_key
    assert "europe-west9/europe-west9-b/c3d-standard-8" in by_key
    assert "europe-west9/europe-west9-c/c3d-standard-8" in by_key
    expanded = by_key["europe-west9/europe-west9-a/c3d-standard-8"]
    assert expanded.is_watchlist is True
    assert expanded.family == "c3d"
    assert expanded.custom_label == "All Paris Zones"
