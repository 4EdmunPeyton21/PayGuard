import sys

from app.config import settings
from app.llm.provider import get_model
from strands import Agent, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    print(f"  [Tool Executed] add(a={a}, b={b})")
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    print(f"  [Tool Executed] multiply(a={a}, b={b})")
    return a * b


def main():
    print("=" * 60)
    print("PayGuard LLM Smoke Test")
    print(f"Provider: {settings.llm_provider}")
    print(f"Model:    {settings.llm_model}")
    print(f"Base URL: {settings.llm_base_url}")
    print("=" * 60)

    if not settings.llm_api_key or "xxx" in settings.llm_api_key:
        print("\n[!] NVIDIA NIM API key is not configured in .env!")
        print("    Current value: " + repr(settings.llm_api_key))
        print("\nPlease obtain a free API key from https://build.nvidia.com")
        print("and update LLM_API_KEY in your .env file.")
        sys.exit(1)

    model = get_model()

    print("\n--- Test 1: One-word completion ---")
    simple_agent = Agent(model=model)
    res1 = simple_agent("Reply with ONLY the single word 'CONFIRMED' and nothing else.")
    print(f"Result: {res1}")

    print("\n--- Test 2: Tool calling (multiply) ---")
    tool_agent = Agent(model=model, tools=[add, multiply])
    res2 = tool_agent("What is 12 multiplied by 9? You must use the multiply tool to find out.")
    print(f"Result: {res2}")

    print("\n[OK] Smoke test completed successfully!")


if __name__ == "__main__":
    main()
