"""Exceptions avec des messages lisibles pour l'utilisateur."""


class OrresError(Exception):
    """Erreur attendue : affichée sans traceback."""


class InputError(OrresError):
    """info.yaml ou images invalides."""


class ToolError(OrresError):
    """Outil externe manquant ou défaillant (FFmpeg, edge-tts, Piper...)."""


class ScriptError(OrresError):
    """Script de narration hors des règles."""


class KlingPending(OrresError):
    """Des clips Kling doivent encore être générés."""
