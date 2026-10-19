"""Use the complete shape iterator with the unchanged invariant comparison."""
import json
from pathlib import Path
import sys

import full_geometry
import audit_manual
import t10_manual_v15_audit

t10_manual_v15_audit.wire_shapes=full_geometry.wire_shapes
audit_manual.main()
output=Path(sys.argv[3])
record=json.loads(output.read_text())
record.update(wire_iterator_policy=full_geometry.POLICY,
              full_geometry_entrypoint=audit_manual.artifact(Path(__file__)),
              full_geometry_iterator=audit_manual.artifact(Path(full_geometry.__file__)))
output.write_text(json.dumps(record,indent=2)+'\n')
