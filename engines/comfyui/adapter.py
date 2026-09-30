"""ComfyUI engine adapter — open-video drives ComfyUI via its HTTP API.
open-video is the director; ComfyUI is the hands. This is the seam."""
import json, time, urllib.request, urllib.error
from urllib.parse import urlencode
from pathlib import Path

from open_video.core.http import post_json


class ComfyUIAdapter:
    id = "comfyui"

    def __init__(self, server: str = "http://127.0.0.1:8188", client_id: str = "open-video",
                 output_dir: str = "output"):
        self.server = server.rstrip("/")
        self.client_id = client_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _json(self, url, data=None, timeout=30):
        if data is not None:
            return post_json(url, data, timeout=timeout)
        with urllib.request.urlopen(
                urllib.request.Request(url, headers={"Content-Type": "application/json"}),
                timeout=timeout) as r:
            return json.loads(r.read())

    def health(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.server}/system_stats", timeout=3).read()
            return True
        except Exception:
            return False

    def submit(self, workflow: dict, timeout: int = 30) -> str:
        """POST a workflow (/prompt); raise on validation errors, else return prompt_id."""
        r = self._json(f"{self.server}/prompt",
                       {"prompt": workflow, "client_id": self.client_id}, timeout)
        if r.get("node_errors") or r.get("error"):
            raise RuntimeError(f"workflow rejected: {str(r.get('node_errors') or r.get('error'))[:400]}")
        return r["prompt_id"]

    def wait(self, prompt_id: str, timeout: int = 1800, poll: float = 3.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                h = self._json(f"{self.server}/history/{prompt_id}", timeout=10)
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                h = {}
            if prompt_id in h:
                return h[prompt_id].get("status", {})
            time.sleep(poll)
        return {"status_str": "timeout"}

    def fetch_outputs(self, prompt_id: str, save_node: str = "save_video") -> list:
        """Download the generated files from the save node to output_dir; return local paths."""
        try:
            h = self._json(f"{self.server}/history/{prompt_id}", timeout=10)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []
        outs = (h.get(prompt_id, {}).get("outputs", {})).get(save_node, {}) or {}
        saved = []
        ts = int(time.time())
        for g in outs.get("gifs", []) or outs.get("videos", []) or outs.get("images", []):
            fn, sub = g.get("filename"), g.get("subfolder", "")
            if not fn:
                continue
            url = f"{self.server}/view?{urlencode({'filename': fn, 'subfolder': sub, 'type': 'output'})}"
            p = self.output_dir / f"{ts}_{fn}"
            urllib.request.urlretrieve(url, p)
            saved.append(str(p))
        return saved

    def submit_and_wait(self, workflow: dict, timeout: int = 1800, save_node: str = "save_video") -> dict:
        """One-shot: submit → wait → fetch. Returns {prompt_id, status, outputs}."""
        pid = self.submit(workflow, timeout=30)
        status = self.wait(pid, timeout)
        outputs = self.fetch_outputs(pid, save_node) if status.get("status_str") == "success" else []
        return {"prompt_id": pid, "status": status, "outputs": outputs}
