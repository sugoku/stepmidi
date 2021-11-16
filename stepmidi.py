#    _____ __             __  ___________  ____
#   / ___// /____  ____  /  |/  /  _/ __ \/  _/
#   \__ \/ __/ _ \/ __ \/ /|_/ // // / / // /  
#  ___/ / /_/  __/ /_/ / /  / // // /_/ // /   
# /____/\__/\___/ .___/_/  /_/___/_____/___/   
#              /_/                             

# StepMIDI by @sugoku
# converts between rhythm game file formats and MIDI
# SPDX-License-Identifier: MIT

# currently this code is only made so I can convert between sheet music and gitadora drum, ultimately

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Type, List
import sys
import mido
import simfile
from simfile.notes import Note as NoteSM
from simfile.notes import NoteType, NoteData
from simfile.timing import Beat, BeatValue, BeatValues
from simfile.ssc import SSCSimfile, SSCChart

from config import *

@dataclass
class Note:
    pitch: int  # MIDI, 0-127
    beat_start: float
    beat_end: float
    '''measure: int
    start: Fraction  # in measures
    length: Fraction   # in measures

    def get_midi_on_time(self, ppq: int) -> float:
        return ppq * (some_timesig_thing) * (self.measure + float(self.start))
    def get_midi_off_time(self, ppq: int) -> float:
        return ppq * (Some_timesig_thing) * (self.measure + float(self.start) + float(self.length))'''

@dataclass
class Track:  # also Chart
    name: str = ''
    notes: List[Note] = field(default_factory=list)
    difficulty: int = 10

@dataclass
class Tempo:  # tempo event
    start: float = 0.0  # in measures
    value: float = 120.0
    
@dataclass
class TimeSig:  # time signature event
    start: float = 0.0  # in measures
    numerator: int = 0
    denominator: int = 0

@dataclass
class Song:
    tracks: List[Track] = field(default_factory=list)
    title: str = 'a song'
    artist: str = 'github.com/sugoku'
    tempos: List[Tempo] = field(default_factory=list)
    timesignatures: List[TimeSig] = field(default_factory=list)
    ppq: int = 0
    # time signature is not used in MIDI or SSC so don't worry about that

    def to_midi(self):
        pass
    def to_ssc(self):
        sim = SSCSimfile.blank()
        
        sim.title = self.title
        sim.artist = self.artist

        t_vals = sorted(BeatValue(tempo.start, tempo.value) for tempo in self.tempos)
        if not len(t_vals):
            t_vals = [BeatValue(0.0, 120.0)]
        sim.bpms = str(BeatValues([t for n, t in enumerate(t_vals) if t.value not in [x.value for x in t_vals[:n]]]))
        # based on simfile BeatValues __str__ function
        sim.timesignatures = ',\n'.join(f'{ts.start}={ts.numerator}={ts.denominator}' for ts in self.timesignatures)
        # print(sim.bpms)
        
        for track in self.tracks:
            if not len(track.notes):
                continue

            chart = SSCChart.blank()
            chart.stepstype = gamemode
            chart.difficulty = track.difficulty

            notes = []
            for note in track.notes:
                if note.pitch not in midi_to_gddm:
                    continue
                notes.append(NoteSM(Beat(note.beat_start), midi_to_gddm[note.pitch], NoteType.TAP))
                continue
                if (note.beat_end - note.beat_start) < 0.125:
                    # beat, column, type
                    notes.append(NoteSM(Beat(note.beat_start), midi_to_gddm[note.pitch], NoteType.TAP))
                    # to do: if pedal on off beat 16th/24th/whatever and previous and next 16th/24th is a kick pedal, do left pedal instead
                    # this can be done afterwards
                else:
                    notes.append(NoteSM(Beat(note.beat_start), midi_to_gddm[note.pitch], NoteType.HOLD_HEAD))
                    notes.append(NoteSM(Beat(note.beat_end), midi_to_gddm[note.pitch], NoteType.TAIL))

            if not len(notes):
                continue

            nd = NoteData.from_notes(sorted(notes), 10)
            chart.notes = str(nd)

            sim.charts.append(chart)

        # print(sim.charts)

        return sim

    @classmethod
    def from_midi(cls: Song, midi: mido.MidiFile) -> Song:
        s = Song()
        s.ppq = midi.ticks_per_beat
        # print(s.ppq)

        # print(len(midi.tracks))
        for mt in midi.tracks:
            t = Track()
            for i in range(1, len(mt)):
                mt[i].time += mt[i-1].time
            mt.sort(key=lambda m: m.time)

            # for event in mt:
            #     print(event.time)

            s.tempos += [Tempo(msg.time / midi.ticks_per_beat, mido.tempo2bpm(msg.tempo)) for msg in mt if msg.type == 'set_tempo']
            s.timesignatures += [TimeSig(msg.time / midi.ticks_per_beat, msg.numerator, msg.denominator) for msg in mt if msg.type == 'time_signature']

            note_ons = deque([msg for msg in mt if msg.type == 'note_on' and msg.velocity > 0])
            note_offs = [msg for msg in mt if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)]

            while len(note_ons):
                on_msg = note_ons.popleft()

                i = 0
                while i < len(note_offs):
                    off_msg = note_offs[i]
                    if off_msg.note == on_msg.note:
                        # print(on_msg.time)
                        t.notes.append(Note(
                            pitch = on_msg.note,
                            beat_start = on_msg.time / midi.ticks_per_beat,
                            beat_end = off_msg.time / midi.ticks_per_beat
                        ))

                        '''beat_start = on_msg.time // midi.ticks_per_beat,
                            beat_end = 3,
                            measure = on_msg.time // midi.ticks_per_beat / 4,
                            start = Fraction((on_msg.time / midi.ticks_per_beat / 4) % 1.0),
                            length = Fraction((off_msg.time / midi.ticks_per_beat / 4) % 1.0)'''

                        # print(t.notes[-1])
                        del note_offs[i]

                        if not len(note_ons):
                            break
                        on_msg = note_ons.popleft()
                        i = 0
                    else:
                        i += 1

            # print(t)
            s.tracks.append(t)

        return s

    @classmethod
    def from_ssc(cls: Song, ssc) -> Song:
        s = Song()
        return s

def main():
    s = Song.from_midi(mido.MidiFile(sys.argv[1]))
    # print(s.tracks)
    fn = sys.argv[2]
    with open(fn, 'w') as f:
        ssc = s.to_ssc()
        # print(ssc)
        ssc.serialize(f)

if __name__ == '__main__':
    main()