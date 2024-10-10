# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


class ConversionPhase:
    """
    Conversion phase to hold name and logging-friendly name.
    """

    def __init__(self, name, log_name=None):  # type: (str, str|None) -> None
        self.name = name
        self.log_name = log_name
        self.last_stage = None  # type: ConversionPhase|None

    def __str__(self):
        return self.log_name if self.log_name else self.name

    def __repr__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, value):
        return self.__hash__() == value.__hash__()


class ConversionPhases:
    """During conversion we will be in different states depending on
    where we are in the execution. This class establishes the different phases
    that we have as well as what the current phase is set to.
    """

    POST_CLI = ConversionPhase(name="POST_CLI")
    PREPARE = ConversionPhase(name="PREPARE", log_name="Prepare")
    # PONR means Point Of No Return
    PRE_PONR_CHANGES = ConversionPhase(name="PRE_PONR_CHANGES", log_name="Prepare")
    # Phase to exit the Analyze SubCommand early
    ANALYZE_EXIT = ConversionPhase(name="ANALYZE_EXIT", log_name="Analyzing")
    POST_PONR_CHANGES = ConversionPhase(name="POST_PONR_CHANGES", log_name="Final")
    ROLLBACK = ConversionPhase(name="ROLLBACK", log_name="Rollback")

    current_phase = None  # type: ConversionPhase|None

    @classmethod
    def get(cls, key):  # type: (str) -> ConversionPhase
        return next((phase for phase in cls.__dict__ if isinstance(phase, ConversionPhase) and phase.name == key))

    @classmethod
    def has(cls, key):  # type: (str) -> bool
        try:
            cls.get(key)
            return True
        except StopIteration:
            return False

    @classmethod
    def set_current(cls, phase):  # type: (str|ConversionPhase|None) -> None
        previous_phase = cls.current_phase
        if phase is None:
            cls.current_phase = None
        elif isinstance(phase, str) and cls.has(phase):
            cls.current_phase = cls.get(phase)
        elif isinstance(phase, ConversionPhase) and phase.name in cls.__dict__:
            cls.current_phase = phase
        else:
            raise NotImplementedError("The {} phase is not implemented in the {} class".format(phase, cls.__name__))

        if cls.current_phase:
            cls.current_phase.last_stage = previous_phase

    @classmethod
    def is_current(cls, phase):  # type: (str|ConversionPhase|list[str|ConversionPhase]) -> bool
        if isinstance(phase, str):
            return cls.current_phase == cls.get(phase)
        elif isinstance(phase, ConversionPhase) and phase.name in cls.__dict__:
            return cls.current_phase == phase
        elif isinstance(phase, list):
            return any(cls.is_current(phase_single) for phase_single in phase)
        raise TypeError("Unexpected type, wanted str, {0}, or a list of str or {0}".format(ConversionPhase.__name__))
