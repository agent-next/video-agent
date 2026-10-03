"""MiniMax H3 backend for open-video.

Ports the proven H3 generation (from early lab) behind the model-agnostic
ModelBackend interface. H3 = the #1 open video model (Arena T2V #2 / I2V #3 overall, #1 open,
at parity with closed). Baseline backend for open-video.
"""
from __future__ import annotations
import json, os, shutil, subprocess, uuid
from pathlib import Path
from open_video.core.backend import ModelBackend, Capabilities, ShotRequest, ShotResult

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent            # repo root (source) / open_video pkg dir (wheel)
WORKFLOWS = {"t2v": HERE / "workflows" / "h3_t2v_api.json",
             "i2v": HERE / "workflows" / "h3_flf2v_api.json",
             "flf2v": HERE / "workflows" / "h3_flf2v_api.json",
             "t2v_vdn": HERE / "workflows" / "h3_t2v_vdn_api.json"}


def resolve_comfy_input() -> Path:
    """Absolute ComfyUI ``input/`` dir where reference frames are staged.

    OPEN_VIDEO_COMFYUI_INPUT wins; else derived from the ComfyUI root the rest of
    the project already knows (OPEN_VIDEO_COMFYUI_DIR, $OPEN_VIDEO_LAB/$H3_LAB
    lab layout, sibling lab/, the repo's own ComfyUI checkout). Never CWD-relative —
    an unresolvable runtime raises so the caller fails loudly instead of mkdir-ing
    a wrong dir.
    """
    env = os.environ.get("OPEN_VIDEO_COMFYUI_INPUT", "").strip()
    if env:
        p = Path(env).expanduser()
        if not p.is_dir():
            raise FileNotFoundError(f"OPEN_VIDEO_COMFYUI_INPUT={p} is not a directory")
        return p.resolve()
    roots = []
    comfy_dir = os.environ.get("OPEN_VIDEO_COMFYUI_DIR", "").strip()
    if comfy_dir:
        roots.append(("OPEN_VIDEO_COMFYUI_DIR", Path(comfy_dir).expanduser()))
    for var in ("OPEN_VIDEO_LAB", "H3_LAB"):
        v = os.environ.get(var, "").strip()
        if v:
            roots.append((var, Path(v).expanduser() / "ComfyUI"))
    roots += [(None, REPO_ROOT.parent / "lab" / "ComfyUI"), (None, REPO_ROOT / "ComfyUI")]
    for var, r in roots:
        if r.is_dir():
            return (r / "input").resolve()
        if var:
            raise FileNotFoundError(f"{var} points to a missing ComfyUI directory: {r}")
    raise FileNotFoundError(
        "ComfyUI input dir not found for staging reference frames — set "
        "OPEN_VIDEO_COMFYUI_INPUT (tried: " + ", ".join(str(r / "input") for _, r in roots) + ")")


def _snap_17k5(duration_s: float) -> int:
    """H3 num_frames snaps to 17k+5 @ 24fps (video-VAE temporal constraint)."""
    b = max(5, round(duration_s * 24))
    return b + (5 - (b % 17)) % 17


class H3Backend(ModelBackend):
    id = "minimax-h3"
    display_name = "MiniMax H3 (Hailuo 3.0)"
    capabilities = Capabilities(
        t2v=True, i2v=True, flf2v=True, r2v="r2v" in WORKFLOWS, native_audio=True,
        max_duration_s=15.0, max_short_edge_px=768,
        aspects=("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        strengths=("native-stereo-audio", "prompt-adherence", "arena-top-open"),
    )

    # --- prompt grammar (the official 3-field guide; condensed) ---
    def prompt_guide(self) -> str:
        if (HERE / "PROMPT_GRAMMAR.md").exists():
            return (HERE / "PROMPT_GRAMMAR.md").read_text()
        return ("H3 3-field: integrated_multimodal_description (style-first [Shot 1], bracketed shots w/ "
                "increasing cut times, camera type+amplitude+speed prose, <d>[lang] verbatim</d> dialogue "
                "w/ (S1)/(S2) IDs) + overall_soundscape (1-4 sent) + non_diegetic_music (1-3 sent, "
                "instrumentation/tempo only). Optional instruction line for I2V/FL2VA/L2VA.")

    def craft_prompt(self, intent: dict, mode: str) -> str:
        """intent = {subject, action, camera, environment, soundscape, music, dialogue[], first_frame_ref?}.
        Basic template; the core's LLM crafter can override with a richer model-specific prompt."""
        instr = ""
        if mode == "i2v":
            instr = ("For the target video, at 0.00 seconds into the target video, <Picture 1> "
                     "(from [Shot 1]) is fully referenced.\n\n")
        elif mode == "flf2v":
            instr = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) "
                     "aligns with the 0.00-second mark; Picture 2 aligns with the final timestamp.\n\n")
        cam = intent.get("camera", "The camera pushes in with small amplitude at slow speed")
        d = intent.get("dialogue") or []
        dlg = ""
        for i, line in enumerate(d):
            sp = line.get("speaker", f"S{i+1}")
            lang = line.get("lang", "English")
            dlg += f" {sp} says: <d>[{lang}] {line['text']}</d>"
        return (f"{instr}integrated_multimodal_description: [Shot 1] Live-action, cinematic, "
                f"a medium shot frames {intent.get('subject','the subject')}. {cam} as "
                f"{intent.get('action','the scene unfolds with natural motion')}.{dlg}\n\n"
                f"overall_soundscape: {intent.get('soundscape','ambient environmental sounds with subtle physical motion.')}\n\n"
                f"non_diegetic_music: {intent.get('music','a soft minimal ambient score at a slow tempo.')}")

    def constraints(self) -> dict:
        return {"duration_range_s": (4, 15), "frame_grid": "17k+5 @ 24fps",
                "max_refs": {"images": 9, "videos": 3, "audios": 3, "total": 12},
                "resolution_multiple": 32, "min_short_edge_px": 384,
                "audio": "32kHz stereo native", "guidance": "CFG-distilled (no neg prompt/guidance)"}

    def default_settings(self) -> dict:
        return {"steps": 20, "sampler": "res_multistep", "scheduler": "simple",
                "shift_video": 12.0, "shift_audio": 3.0,
                "diffusion_quant": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                "text_encoder_quant": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
                "video_vae": "minimax_h3_video_vae_fp16.safetensors",
                "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
                "engine_flags": "--lowvram --use-sage-attention",
                "known_issues": {"NVFP4": "avoid on 5090 (ComfyUI #14157)"}}

    def settings_profiles(self) -> dict:
        """Named settings variants selectable per shot via ``req.extra['settings_profile']``.

        ``vdn_dmd8`` runs the OpenVDN DMD-distilled branch (8 NFE, shifts 12/3 fixed
        by the execution-plan node) on the same pruned INT8/ConvRot base via the
        minimax-h3-audio-T8 custom node. ~2.5x fewer steps than default; judge the
        quality delta before making it a default. No LoRA stacking (VDN owns MODEL).
        Weights: MiniMax H3 Community License — territory excludes EU/UK/KR/US.
        """
        base = self.default_settings()
        return {
            "default": base,
            "vdn_dmd8": {
                **{k: v for k, v in base.items() if k not in ("steps", "sampler", "scheduler", "known_issues")},
                "steps": 8,
                "sampler": "vdn_native_euler (plan node)",
                "scheduler": "vdn_dmd8_sigma_schedule (plan node)",
                "shift_video": 12.0, "shift_audio": 3.0,
                "workflow": "t2v_vdn",
                "custom_node": "minimax-h3-audio-T8 (GPL-3.0, runtime-only dep)",
                "weights": "OpenVDN/vdn-minimax-h3 stage_dmd_8nfe (models/diffusion_models/OpenVDN/)",
                "license_note": "MiniMax H3 Community License: territory excludes EU/UK/KR/US",
                "modes": ("t2v",),
                "no_lora_stacking": True,
            },
        }

    def duration_to_length(self, duration_s: float) -> int:
        return _snap_17k5(duration_s)

    def resolution_for(self, aspect: str, megapixels: float = 1.0) -> tuple:
        # native canvas = 768 short edge, capped 768x1344, multiple of 32
        from math import sqrt
        ax = {"21:9": (21, 9), "16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1),
              "3:4": (3, 4), "9:16": (9, 16)}.get(aspect, (16, 9))
        short = 768
        aw, ah = ax
        if aw >= ah:
            w = int(round(short * aw / ah / 32) * 32); h = short
        else:
            h = int(round(short * ah / aw / 32) * 32); w = short
        return (w, h)

    def generate(self, req: ShotRequest, engine=None) -> ShotResult:
        """Build the ComfyUI workflow for this shot, stage any images, run via the engine adapter."""
        profiles = self.settings_profiles()
        profile = req.extra.get("settings_profile", "default")
        if profile not in profiles:
            return ShotResult(ok=False, error=f"H3 settings profile '{profile}' unknown "
                              f"(have: {', '.join(profiles)})")
        s = profiles[profile]
        wf_key = s.get("workflow", req.mode) if profile != "default" else req.mode
        if profile != "default" and req.mode not in s.get("modes", (req.mode,)):
            return ShotResult(ok=False, error=f"H3 profile '{profile}' does not support mode '{req.mode}'")
        wf_path = WORKFLOWS.get(wf_key)
        if not wf_path:
            return ShotResult(ok=False, error=f"H3 mode '{req.mode}' unsupported")
        wf = json.loads(wf_path.read_text())
        wf["h3_i2v"]["inputs"].update({"prompt": req.prompt, "width": req.width,
                                       "height": req.height, "length": _snap_17k5(req.duration_s)})
        wf["noise"]["inputs"]["noise_seed"] = req.seed
        if "sigmashift" in wf:  # VDN plan node fixes shifts itself
            wf["sigmashift"]["inputs"].update({"shift_video": s["shift_video"], "shift_audio": s["shift_audio"]})
        if "scheduler" in wf:
            wf["scheduler"]["inputs"]["steps"] = s["steps"]
        # LoRA support (community fine-tuned style/domain enhancers — the SD-flywheel for video)
        if req.lora and s.get("no_lora_stacking"):
            return ShotResult(ok=False, error=f"H3 profile '{profile}' owns MODEL patches; "
                              "LoRA stacking is not supported (VDN composer contract)")
        if req.lora:
            wf["lora_loader"] = {"class_type": "LoraLoader", "inputs": {
                "model": ["load_unet", 0], "clip": ["load_clip", 0], "lora_name": req.lora,
                "strength_model": req.lora_weight, "strength_clip": 0.0}}
            wf["sigmashift"]["inputs"]["model"] = ["lora_loader", 0]  # rewire model through LoRA
        if req.trigger_word:
            wf["h3_i2v"]["inputs"]["prompt"] = f"{req.trigger_word}, {req.prompt}"
        # stage reference frames for I2V/FL2VA (per-run filenames: no cross-run collisions)
        if req.mode in ("i2v", "flf2v"):
            refs = [("first_frame", req.first_frame)]
            if req.mode == "flf2v":
                refs.append(("last_frame", req.last_frame))
            for name, p in refs:
                if not p:
                    return ShotResult(ok=False, error=f"H3 mode '{req.mode}' requires {name}")
                if not Path(p).is_file():
                    return ShotResult(ok=False, error=f"H3 {name} not readable: {p}")
            try:
                staging = resolve_comfy_input()
                staging.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return ShotResult(ok=False, error=f"staging dir: {e}")
            tag = uuid.uuid4().hex[:8]
            try:
                ff_name = f"ov_ff_{req.seed}_{tag}{Path(req.first_frame).suffix or '.png'}"
                shutil.copy(req.first_frame, staging / ff_name)
                wf["load_firstframe"]["inputs"]["image"] = ff_name
                if req.mode == "flf2v":
                    lf_name = f"ov_lf_{req.seed}_{tag}{Path(req.last_frame).suffix or '.png'}"
                    shutil.copy(req.last_frame, staging / lf_name)
                    wf["load_lastframe"]["inputs"]["image"] = lf_name
                else:  # i2v: drop the last-frame branch
                    wf["h3_i2v"]["inputs"].pop("last_frame", None); wf.pop("load_lastframe", None)
            except OSError as e:
                return ShotResult(ok=False, error=f"stage refs: {e}")
        wf["save_video"]["inputs"]["filename_prefix"] = f"ov_{req.mode}"
        # run
        if engine is None:
            from open_video.engines.comfyui.adapter import ComfyUIAdapter
            engine = ComfyUIAdapter()
        try:
            res = engine.submit_and_wait(wf, timeout=1800, save_node="save_video")
        except Exception as e:
            return ShotResult(ok=False, error=f"engine: {e}")
        if res["status"].get("status_str") != "success":
            return ShotResult(ok=False, error=res["status"].get("status_str", "failed"),
                              receipt={"prompt_id": res["prompt_id"], "status": res["status"]})
        outputs = res.get("outputs") or []
        receipt = {"prompt_id": res["prompt_id"], "engine": engine.id, "outputs": outputs,
                   "model": self.id, "mode": req.mode, "seed": req.seed,
                   "width": req.width, "height": req.height,
                   "duration_s": _snap_17k5(req.duration_s) / 24,
                   "steps": s["steps"], "sampler": s["sampler"], "scheduler": s["scheduler"],
                   "lora": req.lora, "lora_weight": req.lora_weight if req.lora else None}
        if not outputs:
            return ShotResult(ok=False, error="engine reported success but returned no video",
                              receipt=receipt)
        return ShotResult(ok=True, video_path=outputs[0], receipt=receipt)
