"""Import the separate, task-local MMA-inspired numerical profile."""
import sys
from t10_common import DEFAULT_BENCHMARK_ROOT

if str(DEFAULT_BENCHMARK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_BENCHMARK_ROOT))

from benchmark.tasks.T10.public.matmul_oracle_mma import *  # noqa: F403
