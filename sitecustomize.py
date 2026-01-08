"""
Auto-load `.env` when running Python from this repository.

This makes simple commands like:
  python -c "import os; print(os.getenv('LLM_API_KEY'))"
work as expected for operators.

No logging and no secret printing happens here.
"""

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

