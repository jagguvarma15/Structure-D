"""Tests for configuration loading."""

from structure_d.config import Settings, load_settings


def test_default_settings():
    """Settings should have sensible defaults even without a config file."""
    settings = Settings()
    assert settings.project_name == "structure-d"
    assert settings.log_level == "INFO"
    assert settings.ingestion.ocr_enabled is True
    assert settings.preprocessing.chunking.max_tokens == 1024


def test_load_settings_from_yaml(tmp_path):
    """Settings should load from a YAML file."""
    config = tmp_path / "test.yaml"
    config.write_text(
        "project_name: test-project\n"
        "log_level: DEBUG\n"
        "ingestion:\n"
        "  ocr_enabled: false\n"
    )
    settings = load_settings(config)
    assert settings.project_name == "test-project"
    assert settings.log_level == "DEBUG"
    assert settings.ingestion.ocr_enabled is False


def test_load_settings_missing_file():
    """Should return defaults if the file doesn't exist."""
    settings = load_settings("/nonexistent/path.yaml")
    assert settings.project_name == "structure-d"
