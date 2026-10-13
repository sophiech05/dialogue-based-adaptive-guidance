"""Reusable Whisper adapter; importing this module never loads a model."""
import os

def transcribe_clip(clip, settings):
    if settings.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
    else:
        os.environ.pop('HF_HUB_OFFLINE', None)
    import mlx_whisper
    return mlx_whisper.transcribe(
        clip, path_or_hf_repo=settings.model, language=settings.language,
        task='transcribe', initial_prompt=settings.initial_prompt or None,
        condition_on_previous_text=False,
    )
