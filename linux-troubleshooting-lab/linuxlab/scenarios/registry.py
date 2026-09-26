import random
from typing import Dict, List, Optional
from linuxlab.scenarios.base import Scenario
from linuxlab.scenarios.cpu import HighCPUScenario
from linuxlab.scenarios.memory import MemoryPressureScenario
from linuxlab.scenarios.disk import DiskSpaceScenario
from linuxlab.scenarios.inodes import InodeExhaustionScenario
from linuxlab.scenarios.permissions import FilePermissionsScenario, LogFilePermissionScenario
from linuxlab.scenarios.services import ServiceUnavailableScenario, StoppedServiceScenario
from linuxlab.scenarios.networking import PortConflictScenario
from linuxlab.scenarios.logs import ApplicationLogScenario
from linuxlab.scenarios.fluent import (
    StaleLockScenario,
    OpenDeletedFileScenario,
    ServicePortMismatchScenario,
    DisguisedProcessCPUScenario,
    DatabasePortMisconfigurationScenario,
)
from linuxlab.scenarios.advanced import (
    DualLayerDNSFailureScenario,
    ReadOnlyMountScenario,
    MultiLayerRegressionScenario,
    ZombieProcessFloodScenario,
    StealthMemoryLeakScenario,
)
from linuxlab.scenarios.expert import (
    ProductionOutageNetworkScenario,
    MultiServiceDeadlockScenario,
    ShadowedStorageExhaustionScenario,
    MetadataSaturationTimeoutScenario,
    StealthCryptominerScenario,
)

class ScenarioRegistry:
    """Central registry and generator for all troubleshooting scenarios."""

    def __init__(self):
        self._scenarios: Dict[str, Scenario] = {}
        self._register_defaults()

    def _register_defaults(self):
        default_classes = [
            # Level 1: EASY (5)
            HighCPUScenario,                  # cpu_001
            MemoryPressureScenario,           # mem_001
            DiskSpaceScenario,                # disk_001
            FilePermissionsScenario,          # perm_001
            StoppedServiceScenario,           # easy_005

            # Level 2: MODERATE (5)
            InodeExhaustionScenario,          # inode_001
            ServiceUnavailableScenario,       # service_001
            PortConflictScenario,             # net_001
            ApplicationLogScenario,           # log_001
            LogFilePermissionScenario,        # mod_005

            # Level 3: FLUENT (5)
            StaleLockScenario,                    # fluent_001
            OpenDeletedFileScenario,              # fluent_002
            ServicePortMismatchScenario,          # fluent_003
            DisguisedProcessCPUScenario,          # fluent_004
            DatabasePortMisconfigurationScenario, # fluent_005

            # Level 4: ADVANCED (5)
            DualLayerDNSFailureScenario,   # adv_001
            ReadOnlyMountScenario,         # adv_002
            MultiLayerRegressionScenario,  # adv_003
            ZombieProcessFloodScenario,    # adv_004
            StealthMemoryLeakScenario,     # adv_005

            # Level 5: EXPERT (5)
            ProductionOutageNetworkScenario,    # expert_001
            MultiServiceDeadlockScenario,       # expert_002
            ShadowedStorageExhaustionScenario,  # expert_003
            MetadataSaturationTimeoutScenario,  # expert_004
            StealthCryptominerScenario,         # expert_005
        ]
        for cls in default_classes:
            instance = cls()
            self._scenarios[instance.id] = instance

    def register(self, scenario: Scenario):
        """Register a new custom scenario."""
        self._scenarios[scenario.id] = scenario

    def get(self, scenario_id: str) -> Optional[Scenario]:
        """Retrieve scenario by its unique ID."""
        return self._scenarios.get(scenario_id)

    def list_all(self) -> List[Scenario]:
        """Return all registered scenarios."""
        return list(self._scenarios.values())

    def filter(
        self,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        level: Optional[str] = None,
    ) -> List[Scenario]:
        """Filter scenarios by category, difficulty, or learning level."""
        results = []
        for s in self._scenarios.values():
            if category and s.category.lower() != category.lower():
                continue
            
            # Level filter
            s_level = getattr(s, "level", s.difficulty).upper()
            if level and s_level != level.upper():
                continue

            # Difficulty filter (backward-compatible)
            if difficulty:
                d_upper = difficulty.upper()
                if d_upper in ["EASY", "MODERATE", "FLUENT", "ADVANCED", "EXPERT"]:
                    if s_level != d_upper:
                        continue
                elif s.difficulty.upper() != d_upper:
                    # If someone passes legacy 2YOE or PRODUCTION
                    continue

            results.append(s)
        return results

    def get_random(
        self,
        recent_ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        level: Optional[str] = None,
    ) -> Optional[Scenario]:
        """Select a random scenario, avoiding immediate repetition from history."""
        candidates = self.filter(category=category, difficulty=difficulty, level=level)
        if not candidates:
            # Fallback if no matching scenario in category+level, try level alone
            if category and level:
                candidates = self.filter(level=level)
            if not candidates:
                candidates = self.list_all()

        recent_ids = recent_ids or []
        last_id = recent_ids[-1] if recent_ids else None

        # Filter out the immediately preceding scenario if we have alternatives
        filtered = [s for s in candidates if s.id != last_id]
        pool = filtered if filtered else candidates

        return random.choice(pool)

# Global singleton registry
registry = ScenarioRegistry()
