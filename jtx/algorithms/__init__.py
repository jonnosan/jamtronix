"""Algorithm classes — one per generator type in docs/SPEC.md."""

from jtx.algorithms.acid_bass import AcidBass
from jtx.algorithms.arp import Arp
from jtx.algorithms.drum_one_shot import DrumOneShot
from jtx.algorithms.drum_pattern import DrumPattern
from jtx.algorithms.melodic_line import MelodicLine
from jtx.algorithms.sub_drone import SubDrone

__all__ = ["AcidBass", "Arp", "DrumOneShot", "DrumPattern", "MelodicLine", "SubDrone"]
