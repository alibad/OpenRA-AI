"""OpenRA AI's interruptible game companion."""

from .core import Companion
from .models import GameSnapshot, Insight

__all__ = ["Companion", "GameSnapshot", "Insight"]
__version__ = "0.1.0"
