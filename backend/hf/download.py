"""Prefetch every Hugging Face model so MeetBrief works fully offline (e.g. during a demo).

    python -m backend.hf.download            # all models (~8 GB)
    python -m backend.hf.download qa mt      # selected tasks
Afterwards you can run with HF_HUB_OFFLINE=1.
"""
from __future__ import annotations

import os
import sys
import time

# Plain HTTP transfers proved more reliable than the Xet backend on some networks (downloads stalled at 0 KB/s).
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

from backend.hf import models


def main(tasks: list[str]) -> None:
    from huggingface_hub import HfApi, snapshot_download

    tasks = tasks or list(models.MODELS)
    for task in tasks:
        mid = models.MODELS[task]
        t0 = time.time()
        print(f"[{task}] {mid} ...", flush=True)
        files = HfApi().list_repo_files(mid)
        # download one weight format only (prefer safetensors) and skip other frameworks
        ignore = ["*onnx*", "*.msgpack", "*.h5", "*tflite*", "*openvino*", "flax_*", "tf_*", "rust_*", "*.ot", "checkpoint-*/*",
                  "*optimizer*", "*scheduler*", "training_args*", "*.ckpt"]
        if any(f.endswith(".safetensors") for f in files):
            ignore.append("*.bin")
        snapshot_download(mid, ignore_patterns=ignore)
        print(f"[{task}] downloaded in {time.time() - t0:.0f}s", flush=True)
        try:
            models._load(task)
            print(f"[{task}] loads OK", flush=True)
        except Exception as exc:
            print(f"[{task}] FAILED to load: {exc}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
