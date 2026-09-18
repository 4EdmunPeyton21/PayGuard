from app.config import settings


def test_settings_load():
    assert settings.llm_model == "openai/gpt-oss-20b"
    assert settings.ddb_table == "PayGuardCases"
    assert settings.s3_bucket == "payguard-uploads"
