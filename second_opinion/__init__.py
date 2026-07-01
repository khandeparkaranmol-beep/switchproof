"""Second Opinion — an independent, grounded verification layer for AI output."""

# Load .env before anything reads the environment, so the API key is picked up
# automatically on every run (CLI, eval, doctor).
from .config import load_dotenv as _load_dotenv

_load_dotenv()

from .models import Claim, Evidence, Label, Report, Verdict
from .pipeline import Pipeline

__all__ = ["Claim", "Evidence", "Label", "Report", "Verdict", "Pipeline"]
__version__ = "0.1.0"
