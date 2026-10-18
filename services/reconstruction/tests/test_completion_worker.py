import json
from pathlib import Path
import sys

import numpy as np
import open3d as o3d

from respace_reconstruction.instances import InstanceSeed, RescanRequired
from respace_reconstruction.object_completion import complete_object


def test_configured_worker_preserves_measured_shape_and_reuses_billed_checkpoint(tmp_path,capture,monkeypatch):
    manifest,payloads=capture
    inputs=tmp_path/"inputs";inputs.mkdir()
    for name,data in payloads.items():(inputs/name).write_bytes(data)
    working=tmp_path/"working";working.mkdir()
    script=tmp_path/"provider.py"
    script.write_text('''import argparse,json
from pathlib import Path
import open3d as o3d
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
r=json.loads(Path(a.request).read_text());mesh=o3d.io.read_triangle_mesh(r['observed_mesh'])
o3d.io.write_triangle_mesh(a.output,mesh)
Path(a.output).with_suffix('.receipt.json').write_text(json.dumps({'request_fingerprint':r['request_fingerprint'],'cost_usd':0.5}))
counter=Path(a.output).parent/'calls';counter.write_text(str(int(counter.read_text())+1) if counter.exists() else '1')
''')
    monkeypatch.setenv("RESPACE_OBJECT_COMPLETION_COMMAND",json.dumps([sys.executable,str(script)]))
    monkeypatch.setattr("respace_reconstruction.object_completion.close_observed",lambda _:(_ for _ in ()).throw(RescanRequired("model needed")))
    mesh=o3d.geometry.TriangleMesh.create_box(1,1,1);mesh.translate([-.5,-.5,-.5])
    pose=np.eye(4);pose[2,3]=-3
    seed=InstanceSeed("captured-item","captured-item","chair","Chair","furniture",pose,np.ones(3))
    for _ in range(2):
        candidate,details=complete_object(mesh,seed,manifest,inputs,working,[])
        assert candidate.is_watertight() and details["method"]=="configured_object_completion_worker"
    assert (working/seed.id/"calls").read_text()=="1"
    ledger=json.loads((working/"completion-budget.json").read_text())
    assert sum(e["cost_usd"] for e in ledger["entries"].values())==.5
