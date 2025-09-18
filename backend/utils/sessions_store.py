# central sessions store to avoid circular imports
from typing import Dict, Any

sessions: Dict[str, Dict[str, Any]] = {}
