from app.config import settings

PROVIDERS = {"nvidia", "bedrock", "openai", "ollama"}


def get_model():
    s = settings
    if s.llm_provider == "bedrock" and s.use_bedrock_native:
        from strands.models import BedrockModel  # SigV4 path

        return BedrockModel(
            model_id=s.llm_model,
            temperature=s.llm_temperature,
        )

    from strands.models.openai import OpenAIModel  # OpenAI-compatible path

    return OpenAIModel(
        model_id=s.llm_model,
        client_args={
            "base_url": s.llm_base_url,
            "api_key": s.llm_api_key,
        },
        params={
            "temperature": s.llm_temperature,
            "max_tokens": s.llm_max_tokens,
        },
    )
