"""Music beds through Higgsfield audio on Onca's gateway: the arguments of the client's
higgsfield_generate_audio call and the licence record kept next to the video. Pure: the kit never calls
Higgsfield; the client does, after Onca's free price check and the founder's yes."""

from __future__ import annotations

# Licensed training data, instrumental by default; the cheaper second choice.
MODELS = {"elevenlabs_music_v2_5": {"force_instrumental": True}, "sonilo_music": {}}
# Undisclosed training data and open lawsuits: never for a founder's commercial post.
REFUSED = {"seed_audio": "its training data is not disclosed",
           "suno_music": "its training data is the subject of open copyright lawsuits",
           "suno_mashup": "its training data is the subject of open copyright lawsuits"}
MIN_SECONDS, MAX_SECONDS = 5, 300
TERMS_URL = "https://higgsfield.ai/terms-of-use-agreement"
RETRIEVED = "2026-11-12"
POSITION = "Higgsfield allows commercial use of this output (terms s.4.4) but does not clear rights (s.13.2)"


def model_problem(model: str):
    """Why a model may not make a bed, or None when it may."""
    if model in REFUSED:
        return f"{model} is refused for music beds: {REFUSED[model]}; use {' or '.join(MODELS)}"
    if model not in MODELS:
        return f"unknown music model {model!r}; use {' or '.join(MODELS)}"
    return None


def params(model: str, prompt: str, seconds, price_check: bool = False) -> dict:
    """The `params` of higgsfield_generate_audio; with price_check, Onca's free price check (get_cost)."""
    problem = model_problem(model)
    if problem:
        raise ValueError(problem)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("the prompt must describe the music")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError(f"seconds must be {MIN_SECONDS} to {MAX_SECONDS}, got {seconds!r}")
    out = {"model": model, "prompt": prompt.strip(), "duration": int(seconds) if float(seconds).is_integer() else seconds}
    out.update(MODELS[model])
    if price_check:
        out["get_cost"] = True
    return out


def record(model: str, prompt: str, seconds, credits, job_id: str, call_id, now) -> dict:
    """The bed's licence record (music.json): what made it, what it cost, and the founder's legal position."""
    problem = model_problem(model)
    if problem:
        raise ValueError(problem)
    if isinstance(credits, bool) or not isinstance(credits, (int, float)) or credits < 0:
        raise ValueError(f"credits must be a number, got {credits!r}")
    if not job_id:
        raise ValueError("job_id is the Higgsfield job of the run")
    return {"route": "higgsfield", "model": model, "prompt": prompt, "seconds": seconds, "credits": credits,
            "job_id": job_id, "gateway_call_id": call_id, "terms_url": TERMS_URL, "retrieved": RETRIEVED,
            "position": POSITION, "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
