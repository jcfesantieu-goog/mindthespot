"""Test fixtures for MindTheSpot test suite."""

import pytest


@pytest.fixture
def mock_preemption_api_response():
    """Mock capacityHistory response for preemption rate query."""
    return {
        "capacityHistory": [
            {
                "historyType": "PREEMPTION",
                "preemptionHistory": {
                    "dailyPreemptionRates": [
                        {"date": "2026-09-01", "preemptionRate": 0.05},
                        {"date": "2026-09-02", "preemptionRate": 0.04},
                        {"date": "2026-09-03", "preemptionRate": 0.06},
                        {"date": "2026-09-04", "preemptionRate": 0.05},
                        {"date": "2026-09-05", "preemptionRate": 0.12},
                        {"date": "2026-09-06", "preemptionRate": 0.25},
                        {"date": "2026-09-07", "preemptionRate": 0.35},
                    ]
                },
            }
        ]
    }


@pytest.fixture
def mock_price_api_response():
    """Mock capacityHistory response for price query."""
    return {
        "capacityHistory": [
            {
                "historyType": "PRICE",
                "priceHistory": {
                    "priceIntervals": [
                        {
                            "interval": {
                                "startTime": "2025-09-01T00:00:00Z",
                                "endTime": "2026-03-01T00:00:00Z",
                            },
                            "listPrice": {
                                "currencyCode": "USD",
                                "units": "0",
                                "nanos": 150000000,  # $0.1500
                            },
                        },
                        {
                            "interval": {
                                "startTime": "2026-03-01T00:00:00Z",
                                "endTime": None,  # Active current price
                            },
                            "listPrice": {
                                "currencyCode": "USD",
                                "units": "0",
                                "nanos": 182400000,  # $0.1824
                            },
                        },
                    ]
                },
            }
        ]
    }
