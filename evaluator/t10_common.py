"""Repository-relative paths for the independent T10 evaluator package."""
from pathlib import Path

EVALUATOR_ROOT = Path(__file__).resolve().parent
DEFAULT_BENCHMARK_ROOT = EVALUATOR_ROOT.parent
