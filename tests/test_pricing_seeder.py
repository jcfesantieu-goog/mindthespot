"""Unit tests for GCP on-demand pricing calculation and table generation."""

from mindthespot.storage.pricing_seeder import (
    compute_on_demand_price,
    generate_on_demand_pricing_rows,
    parse_vcpus,
)


def test_parse_vcpus():
    assert parse_vcpus("c4a-standard-16") == 16
    assert parse_vcpus("c3-highmem-8") == 8
    assert parse_vcpus("n2-standard-4") == 4
    assert parse_vcpus("e2-micro") == 2
    assert parse_vcpus("t2d-standard-32") == 32
    assert parse_vcpus("custom-instance") == 4  # default fallback


def test_compute_on_demand_price():
    # c4a base rate is 0.04508, europe-west1 multiplier is 1.10
    # For c4a-standard-16: 16 * 0.04508 * 1.10 = 0.793408
    price_ew1 = compute_on_demand_price("europe-west1", "c4a-standard-16", "c4a")
    assert round(price_ew1, 4) == 0.7934

    # us-central1 multiplier is 1.00
    price_usc1 = compute_on_demand_price("us-central1", "c4a-standard-16")
    assert round(price_usc1, 4) == 0.7213


def test_generate_on_demand_pricing_rows():
    rows = generate_on_demand_pricing_rows()
    assert len(rows) > 1000

    sample = rows[0]
    assert "region" in sample
    assert "machine_type" in sample
    assert "family" in sample
    assert "vcpus" in sample
    assert "memory_gb" in sample
    assert "hourly_price" in sample
    assert "updated_at" in sample
    assert sample["hourly_price"] > 0

