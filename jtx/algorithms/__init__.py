"""Algorithm classes — one per generator type in docs/SPEC.md."""

from jtx.algorithms.acid_bass import AcidBass
from jtx.algorithms.arp import Arp
from jtx.algorithms.cc_lfo import CCLFO, CCEnvelope
from jtx.algorithms.drum_one_shot import DrumOneShot
from jtx.algorithms.drum_pattern import DrumPattern
from jtx.algorithms.melodic_line import MelodicLine
from jtx.algorithms.motif_phrase import MotifPhrase
from jtx.algorithms.noise_riser import NoiseRiser
from jtx.algorithms.reese_bass import ReeseBass
from jtx.algorithms.reference import RootPulse
from jtx.algorithms.step_cc import StepCC
from jtx.algorithms.sub_drone import SubDrone
from jtx.algorithms.sustained_chord import ChordStab, SustainedChord
from jtx.algorithms.voice_follower import VoiceFollower

__all__ = [
    "AcidBass",
    "Arp",
    "CCEnvelope",
    "CCLFO",
    "ChordStab",
    "DrumOneShot",
    "DrumPattern",
    "MelodicLine",
    "MotifPhrase",
    "NoiseRiser",
    "ReeseBass",
    "RootPulse",
    "StepCC",
    "SubDrone",
    "SustainedChord",
    "VoiceFollower",
]
