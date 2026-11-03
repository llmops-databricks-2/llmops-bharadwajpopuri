"""Your first test: project_config.yml loads with the course's ProjectConfig for dev.

`ci.yml` runs every test under tests/ on each pull request and each push to main; add yours here.
"""

from pathlib import Path

from arxiv_curator.config import ProjectConfig

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "project_config.yml"


def test_project_config_loads_for_dev() -> None:
    """Load the provisioned settings without requiring optional lecture resources."""
    cfg = ProjectConfig.from_yaml(str(PROJECT_CONFIG), "dev")

    assert cfg.full_volume_path == "llmops_dev.bharadwajpopuri.evidence_files"
    assert cfg.warehouse_id == "65d92a5dcf046c9d"
    # The two embedding names (README, "Models"): the serving endpoint for ai_query, the gateway service for the client.
    assert cfg.embedding_endpoint == "databricks-gte-large-en"
    assert cfg.embedding_service == "course_ops.gateway.embed"
    # Provisioned values the retrieval foundation reads (lecture 2): the Lakebase project and the usage policy.
    assert cfg.lakebase_instance == "lb-llmops-bharadwajpopuri"
    assert cfg.usage_policy_id == "995f545e-7885-3c66-9825-046d051e0122"
