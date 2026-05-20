"""数据模型."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class InspectionResult:
    """一次巡检聚合结果."""

    host: str
    mock: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    system: Dict[str, Any] = field(default_factory=dict)
    thermal: Dict[str, Any] = field(default_factory=dict)
    power: Dict[str, Any] = field(default_factory=dict)
    storage: Dict[str, Any] = field(default_factory=dict)
    event_log: Dict[str, Any] = field(default_factory=dict)
    version: Dict[str, Any] = field(default_factory=dict)
    faults: List[Dict[str, Any]] = field(default_factory=list)
    api_results: List[Dict[str, Any]] = field(default_factory=list)
    inspection_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d
