import os
import tempfile
from pathlib import Path

# Keep integration-test writes isolated from the persistent development database.
_test_home = Path(tempfile.mkdtemp(prefix="eh4000-api-tests-"))
os.environ["EH4000_DB_PATH"] = str(_test_home / "qa-test.sqlite3")
