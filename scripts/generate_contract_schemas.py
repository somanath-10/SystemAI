from pathlib import Path
import json

from systemai.contracts.models import (
    ActionIntent, ActionResult, CapabilityDefinition, CapabilityTokenClaims,
    GoalContract, Observation, ResourceLease, VerificationResult,
)

MODELS = [GoalContract, ActionIntent, ActionResult, Observation, VerificationResult, CapabilityDefinition, ResourceLease, CapabilityTokenClaims]
root = Path(__file__).parents[1] / "contracts" / "schema"
root.mkdir(parents=True, exist_ok=True)
for model in MODELS:
    (root / f"{model.__name__}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True))
print(f"wrote {len(MODELS)} schemas to {root}")
