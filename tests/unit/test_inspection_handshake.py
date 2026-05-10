import pytest

from app.services.agent_deploy_service import validate_descriptor_against_inspection


def test_validate_descriptor_against_inspection_rejects_missing_module() -> None:
    descriptor = {
        "modules": [{"id": "email_delivery"}],
        "compatibility": {"runtime_api": "v2"},
    }
    inspection = {
        "modules": ["summary_generation"],
        "triggers": ["manual"],
        "runtime_api": "v2",
    }
    with pytest.raises(ValueError, match="email_delivery"):
        validate_descriptor_against_inspection(descriptor, inspection)
