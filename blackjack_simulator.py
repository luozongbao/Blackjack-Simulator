"""
Blackjack Monte Carlo Simulator
================================
A flexible Blackjack simulation supporting various rule variations,
basic strategy, and multiple betting strategies.

Usage:
    python blackjack_simulator.py                  # run with defaults
    python blackjack_simulator.py --num-games 50000 --num-decks 8
    python blackjack_simulator.py --strategy martingale --max-bet 5000
    python blackjack_simulator.py --help            # show all options
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ----------------------------------------------------------------------
# Cards & Deck
# ----------------------------------------------------------------------

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']


class Card:
    __slots__ = ('rank', 'suit')

    def __init__(self, rank: str, suit: str = ''):
        self.rank = rank
        self.suit = suit

    @property
    def value(self) -> int:
        """Blackjack point value (ace returns 1; 11 handled by Hand)."""
        if self.rank in ('J', 'Q', 'K'):
            return 10
        if self.rank == 'A':
            return 1
        return int(self.rank)

    def __repr__(self) -> str:
        return f"{self.rank}{self.suit}"


# Hi-Lo card counting tags
def hilo_value(card: Card) -> int:
    """Hi-Lo tag for a single card: 2-6 = +1, 7-9 = 0, 10/A/J/Q/K = -1."""
    if card.rank in ('2', '3', '4', '5', '6'):
        return 1
    if card.rank in ('10', 'J', 'Q', 'K', 'A'):
        return -1
    return 0  # 7, 8, 9


class Deck:
    """A shoe of one or more 52-card decks with optional auto-shuffler."""

    def __init__(
        self,
        num_decks: int = 6,
        auto_shuffler: bool = False,
        penetration: float = 0.75,
    ):
        self.num_decks = num_decks
        self.auto_shuffler = auto_shuffler
        self.penetration = penetration  # reshuffle when this fraction dealt
        self.cards: List[Card] = []
        self._initial_count = 0
        self.shuffles = 0
        self.running_count: int = 0  # Hi-Lo running count; reset on shuffle
        self.shuffle()

    def _build(self) -> None:
        self.cards = [
            Card(rank, suit)
            for _ in range(self.num_decks)
            for suit in SUITS
            for rank in RANKS
        ]
        self._initial_count = len(self.cards)

    def shuffle(self) -> None:
        self._build()
        random.shuffle(self.cards)
        self.shuffles += 1
        self.running_count = 0  # fresh shoe -> fresh count

    def needs_shuffle(self) -> bool:
        if self.auto_shuffler:
            return True
        if self._initial_count == 0:
            return True
        dealt = self._initial_count - len(self.cards)
        return dealt / self._initial_count >= self.penetration

    def deal(self) -> Card:
        if self.needs_shuffle():
            self.shuffle()
        card = self.cards.pop()
        self.running_count += hilo_value(card)
        return card


# ----------------------------------------------------------------------
# Hand
# ----------------------------------------------------------------------

class Hand:
    """A blackjack hand. Tracks bet, doubling, splits, and aces rules."""

    def __init__(self, bet: float = 0.0):
        self.cards: List[Card] = []
        self.bet = bet
        self.doubled = False
        self.from_split = False
        self.from_split_aces = False
        self.surrendered = False

    # ------------------------------------------------------------------
    # Hand mechanics
    # ------------------------------------------------------------------
    def add(self, card: Card) -> None:
        self.cards.append(card)

    def can_split(self) -> bool:
        return len(self.cards) == 2 and self.cards[0].value == self.cards[1].value

    def can_double(self) -> bool:
        return len(self.cards) == 2 and not self.doubled

    # ------------------------------------------------------------------
    # Hand evaluation
    # ------------------------------------------------------------------
    @property
    def values(self) -> List[int]:
        """All possible totals given the number of aces."""
        total = sum(c.value for c in self.cards)
        aces = sum(1 for c in self.cards if c.rank == 'A')
        return [total + 10 * i for i in range(aces + 1)]

    @property
    def best(self) -> int:
        viable = [v for v in self.values if v <= 21]
        return max(viable) if viable else min(self.values)

    @property
    def is_bust(self) -> bool:
        return self.best > 21

    @property
    def is_soft(self) -> bool:
        # Has an ace counted as 11 (i.e. best != min and best <= 21)
        if not any(c.rank == 'A' for c in self.cards):
            return False
        viable = [v for v in self.values if v <= 21]
        return bool(viable) and max(viable) != min(self.values)

    @property
    def is_blackjack(self) -> bool:
        # Natural 21 on first two cards, not from a split
        return (
            len(self.cards) == 2
            and self.best == 21
            and not self.from_split
        )

    def __repr__(self) -> str:
        tag = ''
        if self.is_blackjack:
            tag = ' (BJ)'
        elif self.is_soft and not self.is_bust:
            tag = ' (soft)'
        if self.doubled:
            tag += ' [D]'
        return f"{[repr(c) for c in self.cards]} = {self.best}{tag}"


# ----------------------------------------------------------------------
# Basic Strategy (S17 — stand on soft 17)
# ----------------------------------------------------------------------

# Maps player total / pair value -> dealer up-card -> action code
# Actions: H = Hit, S = Stand, D = Double (else Hit if not allowed), P = Split, R = Surrender
DEALER_KEYS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 'A']

HARD_S17 = {
    4:  {2:'H', 3:'H', 4:'H', 5:'H', 6:'H', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    5:  {2:'H', 3:'H', 4:'H', 5:'H', 6:'H', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    6:  {2:'H', 3:'H', 4:'H', 5:'H', 6:'H', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    7:  {2:'H', 3:'H', 4:'H', 5:'H', 6:'H', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    8:  {2:'H', 3:'H', 4:'H', 5:'H', 6:'H', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    9:  {2:'H', 3:'D', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    10: {2:'D', 3:'D', 4:'D', 5:'D', 6:'D', 7:'D', 8:'D', 9:'D', 10:'H', 'A':'H'},
    11: {2:'D', 3:'D', 4:'D', 5:'D', 6:'D', 7:'D', 8:'D', 9:'D', 10:'D', 'A':'D'},
    12: {2:'H', 3:'H', 4:'S', 5:'S', 6:'S', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    13: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    14: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    15: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'H', 8:'H', 9:'H', 10:'R', 'A':'H'},
    16: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'H', 8:'H', 9:'H', 10:'R', 'A':'R'},
    17: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    18: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    19: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    20: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    21: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
}

# Soft totals: hand is soft when it contains an ace counted as 11
# (A+2=13, A+3=14, ..., A+10=21)
SOFT_S17 = {
    13: {2:'H', 3:'H', 4:'H', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    14: {2:'H', 3:'H', 4:'H', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    15: {2:'H', 3:'H', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    16: {2:'H', 3:'H', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    17: {2:'H', 3:'D', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    18: {2:'S', 3:'D', 4:'D', 5:'D', 6:'D', 7:'S', 8:'S', 9:'H', 10:'H', 'A':'H'},
    19: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    20: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
    21: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
}

PAIRS = {
    'A': {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P', 8:'P', 9:'P', 10:'P', 'A':'P'},
    2:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P', 8:'H', 9:'H', 10:'H', 'A':'H'},
    3:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P', 8:'H', 9:'H', 10:'H', 'A':'H'},
    4:   {2:'H', 3:'H', 4:'H', 5:'P', 6:'P', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    5:   {2:'D', 3:'D', 4:'D', 5:'D', 6:'D', 7:'D', 8:'D', 9:'D', 10:'H', 'A':'H'},
    6:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'H', 8:'H', 9:'H', 10:'H', 'A':'H'},
    7:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P', 8:'H', 9:'H', 10:'H', 'A':'H'},
    8:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P', 8:'P', 9:'P', 10:'P', 'A':'P'},
    9:   {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'S', 8:'P', 9:'P', 10:'S', 'A':'S'},
    10:  {2:'S', 3:'S', 4:'S', 5:'S', 6:'S', 7:'S', 8:'S', 9:'S', 10:'S', 'A':'S'},
}

def _dealer_key(card: Card):
    return card.rank if card.rank == 'A' else card.value


def basic_strategy_action(
    hand: Hand,
    dealer_up: Card,
    can_double: bool,
    can_surrender: bool = False,
    hit_soft_17: bool = False,
) -> str:
    """Return the recommended action: H, S, D, P, or R."""
    dealer = _dealer_key(dealer_up)

    # Pairs (including aces)
    if hand.can_split() and not hand.from_split_aces:
        key = 'A' if hand.cards[0].rank == 'A' else hand.cards[0].value
        action = PAIRS[key][dealer]
        if action == 'P':
            return 'P'

    # Soft totals
    if hand.is_soft and not hand.is_bust:
        total = hand.best
        action = SOFT_S17.get(total, {}).get(dealer, 'S')
        return action

    # Hard totals
    total = hand.best
    action = HARD_S17.get(total, {}).get(dealer, 'S')
    if action == 'R' and not can_surrender:
        action = 'H'
    return action


# ----------------------------------------------------------------------
# Betting strategies
# ----------------------------------------------------------------------

class BettingStrategy:
    """Base betting strategy. Receives last round's result + payout to decide next bet."""

    def __init__(self, base_bet: float, max_bet: float = 10_000.0):
        self.base_bet = base_bet
        self.max_bet = max_bet

    def next_bet(
        self,
        last_result: Optional[str] = None,   # 'win' | 'loss' | 'push' | None
        last_bet: float = 0.0,
        last_payout: float = 0.0,             # signed net (+ profit, - loss)
    ) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        pass

    def get_session_stats(self) -> dict:
        """Return strategy-specific session aggregates (max level, etc.)."""
        return {}


class FlatBet(BettingStrategy):
    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        return self.base_bet


class Martingale(BettingStrategy):
    """Multiply the bet by `multiplier` after every loss; reset to base on a win/push.

    `multiplier` is the growth factor on a loss. Classic martingale uses
    `multiplier = 2.0` (double on loss). Values between 1.0 and 2.0 give a
    gentler progression; values > 2.0 grow faster and hit the bet cap
    sooner. The result is always capped at `max_bet`.
    """
    def __init__(
        self,
        base_bet: float,
        max_bet: float = 10_000.0,
        multiplier: float = 2.0,
    ):
        super().__init__(base_bet, max_bet)
        if multiplier <= 0:
            raise ValueError(f"Martingale multiplier must be > 0, got {multiplier!r}")
        self.multiplier: float = multiplier

    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        if last_result == 'loss' and last_bet > 0:
            return min(last_bet * self.multiplier, self.max_bet)
        return self.base_bet


class ReverseMartingale(BettingStrategy):
    """Double the bet after every win; reset to base after a loss/push."""
    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        if last_result == 'win' and last_bet > 0:
            return min(last_bet * 2, self.max_bet)
        return self.base_bet


class DAlembert(BettingStrategy):
    """Add one unit on a loss, subtract one unit on a win (floor at base)."""
    def __init__(self, base_bet: float, max_bet: float = 10_000.0):
        super().__init__(base_bet, max_bet)
        self._unit = base_bet

    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        if last_result == 'loss':
            self._unit += self.base_bet
        elif last_result == 'win':
            self._unit = max(self.base_bet, self._unit - self.base_bet)
        self._unit = min(self._unit, self.max_bet)
        return self._unit

    def reset(self) -> None:
        self._unit = self.base_bet


class OscarGrind(BettingStrategy):
    """Win exactly 1 unit per cycle; bet grows by 1 unit on a win within cycle."""
    def __init__(self, base_bet: float, max_bet: float = 10_000.0):
        super().__init__(base_bet, max_bet)
        self._cycle_profit = 0.0
        self._current = base_bet

    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        # Apply previous round's net profit to cycle total
        if last_payout:
            self._cycle_profit += last_payout

        # End of cycle: profit reached a full unit, or a loss wiped the session
        if self._cycle_profit >= self.base_bet or (last_result == 'loss' and self._cycle_profit <= -self.base_bet):
            self._cycle_profit = 0.0
            self._current = self.base_bet
        elif last_result == 'win' and 0 < self._cycle_profit < self.base_bet:
            # After a win, the next bet grows by one unit (capped so we don't overshoot target)
            self._current = min(self._current + self.base_bet, self.base_bet * 10)
        elif last_result == 'loss':
            # Loss: keep the same bet
            pass

        self._current = min(self._current, self.max_bet)
        return self._current

    def reset(self) -> None:
        self._cycle_profit = 0.0
        self._current = self.base_bet


class Fibonacci(BettingStrategy):
    """Move up the Fibonacci sequence on a loss, down 2 steps on a win."""
    FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]

    def __init__(self, base_bet: float, max_bet: float = 10_000.0):
        super().__init__(base_bet, max_bet)
        self._idx = 0

    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        if last_result == 'loss':
            self._idx = min(self._idx + 1, len(self.FIB) - 1)
        elif last_result == 'win':
            self._idx = max(0, self._idx - 2)
        return min(self.base_bet * self.FIB[self._idx], self.max_bet)

    def reset(self) -> None:
        self._idx = 0


class Labouchere(BettingStrategy):
    """Cancellation system. Start with a list; bet = first + last unit count."""
    def __init__(self, base_bet: float, max_bet: float = 10_000.0,
                 sequence: Optional[List[int]] = None):
        super().__init__(base_bet, max_bet)
        self._sequence: List[int] = list(sequence or [1, 2, 3, 4, 5])
        self._original = list(self._sequence)

    def next_bet(self, last_result=None, last_bet=0.0, last_payout=0.0) -> float:
        if not self._sequence:
            self._sequence = list(self._original)
        if len(self._sequence) == 1:
            units = self._sequence[0]
        else:
            units = self._sequence[0] + self._sequence[-1]
        bet = min(self.base_bet * units, self.max_bet)

        if last_result == 'win':
            # Remove first and last
            if len(self._sequence) >= 2:
                self._sequence.pop(0)
                self._sequence.pop()
            else:
                self._sequence.clear()
        elif last_result == 'loss':
            # Append the unit count we just risked
            self._sequence.append(units)
        return bet

    def reset(self) -> None:
        self._sequence = list(self._original)


# ----------------------------------------------------------------------
# Alin Level: a "mini-game" layered on top of blackjack outcomes
# ----------------------------------------------------------------------

@dataclass
class AlinLevelConfig:
    """One level of the Alin Level progression."""
    bet_units: int       # bet = base_bet * bet_units
    win_threshold: int   # score at which this level is won (>=)
    loss_threshold: int  # score at which this level is lost (<=), must be < 0


def default_alin_levels() -> List[AlinLevelConfig]:
    """The default 2-level config given in the spec."""
    return [
        AlinLevelConfig(bet_units=1, win_threshold=1, loss_threshold=-5),
        AlinLevelConfig(bet_units=6, win_threshold=1, loss_threshold=-5),
    ]


class AlinLevelStrategy(BettingStrategy):
    """
    Alin's level progression (mini-game on top of BJ outcomes).

    The session is divided into N levels. Each level has its own bet
    (in base units) and two score thresholds: a positive "win" target
    and a negative "loss" floor. The score starts at 0 and is updated
    after each blackjack round:

        net payout > 0  -> score += 1
        net payout < 0  -> score -= 1
        net payout == 0 -> score unchanged

    When the score hits the win threshold, the WIN behavior is:
        - 'step_back' (default): step down one level (clamped at 0).
          A WIN at Level 0 stays at Level 0; a WIN at Level 2 goes to
          Level 1, etc. The session only fully resets when a WIN
          happens at Level 0.
        - 'reset': jump straight back to Level 0 regardless of the
          current level.

    `level_wins` counts only WINs that happen AT Level 0 (i.e. mini-
    games that complete from the bottom). With 'step_back' this is the
    only way to record a level win; with 'reset' a WIN at any level
    also counts because the strategy snaps back to Level 0.

    When the score hits the loss threshold the level is lost: if a
    higher level exists the strategy advances to it (score resets to
    0), otherwise it resets to Level 0.

    The bet placed in the current BJ round is `base_bet * level.bet_units`.
    """

    WIN_BEHAVIORS = ('step_back', 'reset')

    def __init__(
        self,
        base_bet: float,
        max_bet: float = 10_000.0,
        levels: Optional[List[AlinLevelConfig]] = None,
        win_behavior: str = 'step_back',
    ):
        super().__init__(base_bet, max_bet)
        if win_behavior not in self.WIN_BEHAVIORS:
            raise ValueError(
                f"win_behavior must be one of {self.WIN_BEHAVIORS}, got {win_behavior!r}"
            )
        self.levels: List[AlinLevelConfig] = list(levels or default_alin_levels())
        if not self.levels:
            self.levels = default_alin_levels()
        self.win_behavior: str = win_behavior
        self._idx: int = 0
        self._score: int = 0
        self.max_level_reached: int = 0
        self.level_wins: int = 0       # WINs that happened AT Level 0
        self.level_losses: int = 0     # levels that ended in a LOSS
        self.level_step_backs: int = 0 # WINs at Level > 0 (only nonzero with step_back)

    def _current_level(self) -> AlinLevelConfig:
        return self.levels[self._idx]

    def next_bet(
        self,
        last_result: Optional[str] = None,
        last_bet: float = 0.0,
        last_payout: float = 0.0,
    ) -> float:
        # 1) Update running score from the round we just played
        if last_payout > 0:
            self._score += 1
        elif last_payout < 0:
            self._score -= 1
        # else: push / break-even mixed round -> no change

        # 2) Check thresholds for the current level
        cfg = self._current_level()
        if self._score >= cfg.win_threshold:
            # Capture whether the WIN happened AT Level 0 before the
            # index moves; this defines a "mini-game completed" event.
            won_at_level_zero = (self._idx == 0)
            if won_at_level_zero:
                self.level_wins += 1
            else:
                self.level_step_backs += 1

            if self.win_behavior == 'reset':
                self._idx = 0
            else:  # 'step_back'
                self._idx = max(0, self._idx - 1)
            self._score = 0
        elif self._score <= cfg.loss_threshold:
            self.level_losses += 1
            if self._idx + 1 < len(self.levels):
                self._idx += 1
            else:
                self._idx = 0
            self._score = 0

        # 3) Track max level reached (0-indexed; we report 1-indexed max)
        if self._idx > self.max_level_reached:
            self.max_level_reached = self._idx

        return min(self.base_bet * self._current_level().bet_units, self.max_bet)

    def reset(self) -> None:
        self._idx = 0
        self._score = 0
        # Do NOT reset max_level_reached / level_wins / level_losses /
        # level_step_backs: those are session aggregates, not state.

    def get_session_stats(self) -> dict:
        return {
            'current_level': self._idx,           # 0-indexed
            'current_score': self._score,
            'max_level_reached': self.max_level_reached,  # 0-indexed
            'win_behavior': self.win_behavior,
            'level_wins': self.level_wins,         # WINs AT Level 0
            'level_step_backs': self.level_step_backs,  # WINs at higher levels (step_back only)
            'level_losses': self.level_losses,
        }


# ----------------------------------------------------------------------
# Hi-Lo card counting
# ----------------------------------------------------------------------

# Wong's standard 1-1-2-4-8-12-16 spread: TC -> bet units (multiplier on base)
DEFAULT_HILO_RAMP: dict = {
    0: 1, 1: 1, 2: 2, 3: 4, 4: 8, 5: 12, 6: 16,
}


class HiLoCount(BettingStrategy):
    """
    Card-counting Hi-Lo betting strategy.

    The bet is sized by the *true count* (running count divided by estimated
    decks remaining in the shoe). The running count is updated by the Deck
    as cards are dealt: 2-6 contribute +1, 7-9 contribute 0, and 10/J/Q/K/A
    contribute -1. The shoe's running count is reset to 0 on every shuffle.

    The bet is `base_bet * ramp[true_count]`, where `ramp` maps the largest
    true-count threshold the current count is at or above to a unit count.
    For example, with the default Wong ramp (TC >= 0: 1u, >= 1: 1u, >= 2: 2u,
    >= 3: 4u, >= 4: 8u, >= 5: 12u, >= 6: 16u), a true count of 3.2 places a
    4-unit bet. The result is capped at `max_bet`. Negative true counts fall
    back to the minimum 1 unit.

    This strategy does NOT modify play decisions; the player still follows
    basic strategy. It only changes the bet size based on the count.
    """

    def __init__(
        self,
        base_bet: float,
        max_bet: float = 10_000.0,
        deck: Optional['Deck'] = None,
        ramp: Optional[dict] = None,
    ):
        super().__init__(base_bet, max_bet)
        self.deck = deck  # shared reference; set in run_simulation
        self.ramp: dict = dict(ramp or DEFAULT_HILO_RAMP)
        # Running aggregates for the report
        self._tc_sum: float = 0.0
        self._tc_count: int = 0
        self._tc_max: float = float('-inf')
        self._tc_min: float = float('inf')
        self._top_bet_count: int = 0  # rounds at max_bet

    def _true_count(self) -> float:
        if self.deck is None:
            return 0.0
        rc = self.deck.running_count
        cards_left = len(self.deck.cards)
        # Floor decks_remaining at 0.5 to avoid blow-up near the end of the shoe
        decks_remaining = max(0.5, cards_left / 52.0)
        return rc / decks_remaining

    def _units_for_tc(self, tc: float) -> int:
        # Find the largest threshold the TC is at or above
        best_units = 1
        for threshold in sorted(self.ramp.keys()):
            if tc >= threshold:
                best_units = self.ramp[threshold]
        return best_units

    def next_bet(
        self,
        last_result: Optional[str] = None,
        last_bet: float = 0.0,
        last_payout: float = 0.0,
    ) -> float:
        tc = self._true_count()

        # Update running aggregates
        self._tc_sum += tc
        self._tc_count += 1
        if tc > self._tc_max:
            self._tc_max = tc
        if tc < self._tc_min:
            self._tc_min = tc

        units = self._units_for_tc(tc)
        bet = min(self.base_bet * units, self.max_bet)
        if bet >= self.max_bet - 1e-9:
            self._top_bet_count += 1
        return bet

    def reset(self) -> None:
        self._tc_sum = 0.0
        self._tc_count = 0
        self._tc_max = float('-inf')
        self._tc_min = float('inf')
        self._top_bet_count = 0

    def get_session_stats(self) -> dict:
        if self._tc_count == 0:
            return {}
        return {
            'avg_true_count': self._tc_sum / self._tc_count,
            'max_true_count': self._tc_max,
            'min_true_count': self._tc_min,
            'top_bet_rounds': self._top_bet_count,
        }


BETTING_STRATEGIES = {
    'flatbet': FlatBet,
    'martingale': Martingale,
    'reverse_martingale': ReverseMartingale,
    'dalembert': DAlembert,
    # Aliases for D'Alembert under more descriptive names.
    # Simple +1 / -1 base unit per round: lose -> +1 unit, win -> -1 unit (floor at base).
    'unit_progression': DAlembert,
    'plus_minus': DAlembert,
    'oscars_grind': OscarGrind,
    'fibonacci': Fibonacci,
    'labouchere': Labouchere,
    'alin_level': AlinLevelStrategy,
    'hilo': HiLoCount,
}


# ----------------------------------------------------------------------
# Game engine
# ----------------------------------------------------------------------

@dataclass
class Config:
    num_decks: int = 6
    auto_shuffler: bool = False
    penetration: float = 0.75
    hit_soft_17: bool = False
    max_split_hands: int = 4            # 4 = up to 3 re-splits
    double_after_split: bool = True
    allow_surrender: bool = False
    blackjack_payout: float = 1.5       # 3:2
    num_games: int = 10_000
    base_bet: float = 10.0
    max_bet: float = 10_000.0
    betting_strategy: str = 'flatbet'
    labouchere_sequence: str = '1,2,3,4,5'
    # Alin Level strategy: comma-separated per-level config. Length = number of levels.
    alin_bets: str = '1,6'                  # bet in base units per level
    alin_win_thresholds: str = '1,1'        # score target (>=) per level
    alin_loss_thresholds: str = '-5,-5'     # score floor (<=, must be negative) per level
    alin_win_behavior: str = 'step_back'    # 'step_back' (default) | 'reset'
    martingale_multiplier: float = 2.0      # bet growth factor on a loss (1.0 = no growth)
    hilo_ramp: str = '0:1,1:1,2:2,3:4,4:8,5:12,6:16'  # TC:units comma list
    seed: Optional[int] = None
    verbose: bool = False
    print_every: int = 0                # 0 = no progress, else print every N games
    save_json: Optional[str] = None     # if set, save full records to this file


class Game:
    """Plays one round of blackjack and returns the player's net result."""

    def __init__(self, deck: Deck, config: Config):
        self.deck = deck
        self.cfg = config

    def _dealer_play(self, hand: Hand) -> None:
        while True:
            v = hand.best
            if v < 17:
                hand.add(self.deck.deal())
            elif v == 17 and self.cfg.hit_soft_17 and hand.is_soft:
                hand.add(self.deck.deal())
            else:
                break

    def _player_decision(self, hand: Hand, dealer_up: Card) -> str:
        return basic_strategy_action(
            hand,
            dealer_up,
            can_double=hand.can_double() and (not hand.from_split or self.cfg.double_after_split),
            can_surrender=self.cfg.allow_surrender,
            hit_soft_17=self.cfg.hit_soft_17,
        )

    def play(self, bet: float) -> Tuple[float, str, dict]:
        """Play one hand. Returns (net_payout, outcome_label, debug_info)."""
        player = Hand(bet=bet)
        dealer = Hand()

        # Initial deal
        player.add(self.deck.deal())
        dealer.add(self.deck.deal())
        player.add(self.deck.deal())
        dealer.add(self.deck.deal())

        hands: List[Hand] = [player]
        splits_done = 0  # number of splits performed (0 for no split)

        # Natural blackjacks
        dealer_bj = dealer.is_blackjack
        player_bj = player.is_blackjack and not dealer_bj and splits_done == 0
        dealer_only_bj = dealer_bj and not player.is_blackjack

        # If player has natural BJ and dealer doesn't, settle and return.
        # Net profit on a BJ = bet * blackjack_payout (3:2 -> 1.5x profit).
        if player.is_blackjack and not dealer_bj:
            payout = bet * self.cfg.blackjack_payout
            return payout, 'bj', {'splits': 0}

        # If dealer has natural BJ and player doesn't, player loses all initial bet
        if dealer_only_bj:
            return -bet, 'loss', {'splits': 0}

        # Player action loop
        idx = 0
        while idx < len(hands):
            hand = hands[idx]
            idx += 1

            # Split?
            while (
                hand.can_split()
                and len(hands) < self.cfg.max_split_hands
                and splits_done < (self.cfg.max_split_hands - 1)
            ):
                action = self._player_decision(hand, dealer.cards[0])
                if action != 'P':
                    break

                # Perform the split
                second_card = hand.cards.pop()
                new_hand = Hand(bet=hand.bet)
                new_hand.from_split = True
                if hand.cards[0].rank == 'A':
                    hand.from_split_aces = True
                    new_hand.from_split_aces = True
                hand.add(self.deck.deal())
                new_hand.add(self.deck.deal())
                # Insert the new hand after the current one
                hands.insert(idx, new_hand)
                splits_done += 1

            # If split aces: one card each, no further action
            if hand.from_split_aces:
                continue

            # Play the hand
            while True:
                if hand.is_bust:
                    break

                # Surrender allowed only on first 2 cards and not after split aces
                if (
                    self.cfg.allow_surrender
                    and len(hand.cards) == 2
                    and not hand.from_split
                ):
                    surrender_action = self._player_decision(hand, dealer.cards[0])
                    if surrender_action == 'R':
                        hand.surrendered = True
                        break

                action = self._player_decision(hand, dealer.cards[0])

                if action == 'D' and hand.can_double() and (not hand.from_split or self.cfg.double_after_split):
                    hand.doubled = True
                    hand.bet *= 2
                    hand.add(self.deck.deal())
                    break
                if action == 'S':
                    break
                # Default: Hit
                hand.add(self.deck.deal())

        # Dealer plays once
        self._dealer_play(dealer)

        # Settle each hand
        total_payout = 0.0
        hand_results: List[str] = []
        for h in hands:
            if h.surrendered:
                total_payout += -h.bet / 2
                hand_results.append('surrender')
                continue
            if h.is_bust:
                total_payout += -h.bet
                hand_results.append('loss')
                continue
            if dealer.is_bust:
                total_payout += h.bet
                hand_results.append('win')
                continue
            if h.best > dealer.best:
                total_payout += h.bet
                hand_results.append('win')
            elif h.best < dealer.best:
                total_payout += -h.bet
                hand_results.append('loss')
            else:
                # push
                hand_results.append('push')

        # Overall outcome label
        if all(r == 'win' for r in hand_results):
            label = 'win'
        elif all(r == 'loss' for r in hand_results):
            label = 'loss'
        elif all(r == 'push' for r in hand_results):
            label = 'push'
        else:
            # Mixed outcomes are reported as 'mixed'
            label = 'mixed'

        return total_payout, label, {
            'splits': splits_done,
            'hands': hand_results,
            'final_player': [repr(h) for h in hands],
            'final_dealer': repr(dealer),
        }


# ----------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------

@dataclass
class GameRecord:
    game_no: int
    bet: float
    payout: float        # net
    outcome: str         # win | loss | push | bj | mixed
    splits: int
    equity_after: float


@dataclass
class SimulationResult:
    config: Config
    records: List[GameRecord] = field(default_factory=list)
    bettor_stats: dict = field(default_factory=dict)

    # ---- aggregates computed on demand ----
    def summary(self) -> dict:
        recs = self.records
        n = len(recs)
        if n == 0:
            return {}

        bets = [r.bet for r in recs]
        payouts = [r.payout for r in recs]
        equities = [r.equity_after for r in recs]

        # Outcome counts (mixed counts as neither pure win nor pure loss)
        wins = sum(1 for r in recs if r.outcome == 'win' or r.outcome == 'bj')
        losses = sum(1 for r in recs if r.outcome == 'loss')
        pushes = sum(1 for r in recs if r.outcome == 'push')
        bjs = sum(1 for r in recs if r.outcome == 'bj')
        mixed = sum(1 for r in recs if r.outcome == 'mixed')

        total_bet = sum(bets)
        total_payout = sum(payouts)
        total_won = sum(p for p in payouts if p > 0)
        total_lost = -sum(p for p in payouts if p < 0)

        final_equity = equities[-1]
        min_equity = min(equities)
        max_equity = max(equities)

        # Max drawdown
        peak = equities[0]
        max_dd = 0.0
        for e in equities:
            peak = max(peak, e)
            dd = peak - e
            if dd > max_dd:
                max_dd = dd

        ev_per_hand = total_payout / n
        ev_per_bet = total_payout / total_bet if total_bet else 0.0
        expected_return = total_won / n        # avg gross win per round
        expected_loss = total_lost / n         # avg gross loss per round (positive number)
        expected_value = ev_per_hand           # alias

        return {
            'games_played': n,
            'games_won': wins,
            'games_lost': losses,
            'games_pushed': pushes,
            'games_blackjack': bjs,
            'games_mixed': mixed,
            'win_rate': wins / n,
            'lose_rate': losses / n,
            'push_rate': pushes / n,
            'min_bet': min(bets),
            'max_bet': max(bets),
            'avg_bet': total_bet / n,
            'total_bet': total_bet,
            'total_payout': total_payout,
            'total_won': total_won,
            'total_lost': total_lost,
            'ev_per_hand': ev_per_hand,
            'ev_per_bet': ev_per_bet,
            'expected_return_per_hand': expected_return,
            'expected_loss_per_hand': expected_loss,
            'expected_value': expected_value,
            'min_equity': min_equity,
            'max_equity': max_equity,
            'final_equity': final_equity,
            'max_drawdown': max_dd,
            # Strategy-specific aggregates (e.g. Alin Level max level).
            'bettor_stats': self.bettor_stats,
        }


def _parse_alin_levels(config: Config) -> List[AlinLevelConfig]:
    """Parse the alin_* strings on Config into a list of AlinLevelConfig."""
    bets = [int(x) for x in config.alin_bets.split(',') if x.strip()]
    wins = [int(x) for x in config.alin_win_thresholds.split(',') if x.strip()]
    losses = [int(x) for x in config.alin_loss_thresholds.split(',') if x.strip()]
    n = max(len(bets), len(wins), len(losses))
    if not (len(bets) == len(wins) == len(losses) == n and n > 0):
        raise ValueError(
            "Alin Level config: --alin-bets, --alin-win-thresholds and "
            "--alin-loss-thresholds must all be the same non-zero length."
        )
    return [
        AlinLevelConfig(bet_units=bets[i], win_threshold=wins[i], loss_threshold=losses[i])
        for i in range(n)
    ]


def _parse_hilo_ramp(config: Config) -> dict:
    """Parse the hilo_ramp string into a {tc: units} dict."""
    ramp: dict = {}
    for pair in config.hilo_ramp.split(','):
        pair = pair.strip()
        if not pair:
            continue
        if ':' not in pair:
            raise ValueError(
                f"Invalid --hilo-ramp pair {pair!r}. Expected 'TC:units', e.g. '2:2'."
            )
        tc, units = pair.split(':', 1)
        ramp[int(tc.strip())] = int(units.strip())
    if not ramp:
        raise ValueError("--hilo-ramp must contain at least one 'TC:units' pair.")
    return ramp


def run_simulation(config: Config) -> SimulationResult:
    if config.seed is not None:
        random.seed(config.seed)

    deck = Deck(
        num_decks=config.num_decks,
        auto_shuffler=config.auto_shuffler,
        penetration=config.penetration,
    )

    seq = [int(x) for x in config.labouchere_sequence.split(',') if x.strip()]
    bet_class = BETTING_STRATEGIES[config.betting_strategy]
    bet_kwargs = dict(base_bet=config.base_bet, max_bet=config.max_bet)
    if config.betting_strategy == 'labouchere':
        bet_kwargs['sequence'] = seq
    elif config.betting_strategy == 'alin_level':
        bet_kwargs['levels'] = _parse_alin_levels(config)
        bet_kwargs['win_behavior'] = config.alin_win_behavior
    elif config.betting_strategy == 'martingale':
        bet_kwargs['multiplier'] = config.martingale_multiplier
    elif config.betting_strategy == 'hilo':
        bet_kwargs['deck'] = deck
        bet_kwargs['ramp'] = _parse_hilo_ramp(config)
    bettor = bet_class(**bet_kwargs)

    game = Game(deck, config)
    result = SimulationResult(config=config)

    equity = 0.0
    last_result = None
    last_bet = 0.0
    last_payout = 0.0

    for i in range(1, config.num_games + 1):
        bet = bettor.next_bet(last_result, last_bet, last_payout)
        bet = max(bet, config.base_bet)  # never below base
        payout, outcome, _info = game.play(bet)
        equity += payout

        result.records.append(GameRecord(
            game_no=i,
            bet=bet,
            payout=payout,
            outcome=outcome,
            splits=_info.get('splits', 0),
            equity_after=equity,
        ))

        last_result = outcome
        last_bet = bet
        last_payout = payout

        if config.verbose and config.print_every and i % config.print_every == 0:
            print(f"  game {i:>6}  bet={bet:>8.2f}  payout={payout:>+8.2f}  "
                  f"equity={equity:>+10.2f}")

    # Capture strategy-specific session aggregates (e.g. Alin Level max level)
    result.bettor_stats = bettor.get_session_stats()

    return result


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

def _hr(title: str, char: str = '=', width: int = 64) -> str:
    return f"\n{char * width}\n{title}\n{char * width}"


def format_report(result: SimulationResult) -> str:
    cfg = result.config
    s = result.summary()

    out = []
    out.append(_hr("BLACKJACK SIMULATION -- REPORT"))
    out.append("Customization (config):")
    out.append(f"  Number of decks        : {cfg.num_decks}")
    out.append(f"  Auto-shuffler          : {'Yes' if cfg.auto_shuffler else 'No'}")
    out.append(f"  Penetration            : {cfg.penetration:.0%}")
    out.append(f"  Soft 17                : {'Hit' if cfg.hit_soft_17 else 'Stand'}")
    out.append(f"  Max split hands        : {cfg.max_split_hands}")
    out.append(f"  Double after split     : {'Yes' if cfg.double_after_split else 'No'}")
    out.append(f"  Surrender allowed      : {'Yes' if cfg.allow_surrender else 'No'}")
    out.append(f"  Blackjack payout       : {cfg.blackjack_payout}:1")
    out.append(f"  Base bet               : {cfg.base_bet:.2f}")
    out.append(f"  Max bet                : {cfg.max_bet:.2f}")
    out.append(f"  Betting strategy       : {cfg.betting_strategy}")
    out.append(f"  Number of games        : {cfg.num_games}")

    out.append(_hr("BETTING"))
    out.append(f"  Min bet                : {s['min_bet']:>12.2f}")
    out.append(f"  Max bet                : {s['max_bet']:>12.2f}")
    out.append(f"  Average bet            : {s['avg_bet']:>12.2f}")
    out.append(f"  Total bet              : {s['total_bet']:>12.2f}")

    out.append(_hr("OUTCOMES"))
    out.append(f"  Games played           : {s['games_played']:>12d}")
    out.append(f"  Games won              : {s['games_won']:>12d}   (win rate  {s['win_rate']:>7.2%})")
    out.append(f"  Games lost             : {s['games_lost']:>12d}   (lose rate {s['lose_rate']:>7.2%})")
    out.append(f"  Games pushed           : {s['games_pushed']:>12d}   (push rate {s['push_rate']:>7.2%})")
    out.append(f"  Blackjacks (player)    : {s['games_blackjack']:>12d}")
    out.append(f"  Mixed-result rounds    : {s['games_mixed']:>12d}")

    out.append(_hr("PROFIT & LOSS"))
    out.append(f"  Total won              : {s['total_won']:>12.2f}")
    out.append(f"  Total lost             : {s['total_lost']:>12.2f}")
    out.append(f"  Total net payout       : {s['total_payout']:>+12.2f}")
    out.append(f"  EV per hand            : {s['ev_per_hand']:>+12.4f}")
    out.append(f"  EV per unit bet        : {s['ev_per_bet']:>+12.6f}")
    out.append(f"  Expected return/hand   : {s['expected_return_per_hand']:>12.4f}")
    out.append(f"  Expected loss/hand     : {s['expected_loss_per_hand']:>12.4f}")
    out.append(f"  Expected value (EV)    : {s['expected_value']:>+12.4f}")

    out.append(_hr("EQUITY"))
    out.append(f"  Starting equity        : {0.00:>+12.2f}")
    out.append(f"  Final equity           : {s['final_equity']:>+12.2f}")
    out.append(f"  Min equity             : {s['min_equity']:>+12.2f}")
    out.append(f"  Max equity             : {s['max_equity']:>+12.2f}")
    out.append(f"  Max drawdown           : {s['max_drawdown']:>12.2f}")

    out.append(_hr("EQUITY CURVE (sample)"))
    if result.records:
        step = max(1, len(result.records) // 10)
        for r in result.records[::step]:
            out.append(f"  game {r.game_no:>6}  equity={r.equity_after:>+12.2f}")
        # Always show last
        if result.records and result.records[-1].game_no % step != 0:
            r = result.records[-1]
            out.append(f"  game {r.game_no:>6}  equity={r.equity_after:>+12.2f}")

    # Strategy-specific aggregates (Alin Level, etc.)
    bs = s.get('bettor_stats') or {}
    if bs:
        out.append(_hr("STRATEGY STATE"))
        for k, v in bs.items():
            out.append(f"  {k:<22} : {v}")

    out.append('=' * 64 + '\n')
    return '\n'.join(out)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

# Set of long flags that take a value (so the pre-processor can auto-attach
# `-prefixed` values like '-5,-5,-5' that argparse would otherwise misread
# as a new flag).
_VALUED_FLAGS = {
    '--soft-17', '--num-decks', '--penetration', '--max-split-hands',
    '--double-after-split', '--blackjack-payout', '--num-games',
    '--base-bet', '--max-bet', '--strategy', '--labouchere-sequence',
    '--alin-bets', '--alin-win-thresholds', '--alin-loss-thresholds', '--alin-win-behavior',
    '--martingale-multiplier',
    '--hilo-ramp', '--seed', '--print-every', '--save-json',
}


def _attach_dash_values(argv: List[str]) -> List[str]:
    """
    Argparse quirk: a value starting with '-' (e.g. '-5,-5,-5') is parsed
    as a new flag. This pre-processor attaches such tokens to the preceding
    valued option, so both forms work:
        --alin-loss-thresholds -5,-5,-5
        --alin-loss-thresholds=-5,-5,-5
    """
    out: List[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if (
            tok in _VALUED_FLAGS
            and i + 1 < len(argv)
            and argv[i + 1].startswith('-')
            and not argv[i + 1].startswith('--')
            and argv[i + 1] not in _VALUED_FLAGS
        ):
            out.append(f"{tok}={argv[i + 1]}")
            i += 2
        else:
            out.append(tok)
            i += 1
    return out


def parse_args(argv: Optional[List[str]] = None) -> Config:
    if argv is not None:
        argv = _attach_dash_values(list(argv))
    p = argparse.ArgumentParser(
        description="Blackjack Monte Carlo simulator with configurable rules and betting strategies.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    rules = p.add_argument_group("Rules")
    rules.add_argument("--soft-17", choices=['hit', 'stand'], default='stand',
                       help="Dealer action on soft 17")
    rules.add_argument("--num-decks", type=int, default=6, help="Number of decks in the shoe")
    rules.add_argument("--auto-shuffler", action='store_true', help="Auto-shuffler (reshuffle every hand)")
    rules.add_argument("--penetration", type=float, default=0.75,
                       help="Reshuffle when this fraction of the shoe has been dealt")
    rules.add_argument("--max-split-hands", type=int, default=4,
                       help="Maximum number of player hands allowed (including the original)")
    rules.add_argument("--double-after-split", choices=['yes', 'no'], default='yes',
                       help="Allow doubling after a split")
    rules.add_argument("--surrender", action='store_true', help="Allow late surrender")
    rules.add_argument("--blackjack-payout", type=float, default=1.5, help="Blackjack payout (3:2 = 1.5)")

    betting = p.add_argument_group("Betting")
    betting.add_argument("--num-games", type=int, default=10_000, help="Number of rounds to simulate")
    betting.add_argument("--base-bet", type=float, default=10.0, help="Base bet unit")
    betting.add_argument("--max-bet", type=float, default=10_000.0,
                         help="Maximum bet (cap for progression strategies)")
    betting.add_argument("--strategy", default='flatbet',
                         choices=list(BETTING_STRATEGIES.keys()),
                         help="Betting strategy")
    betting.add_argument("--labouchere-sequence", default='1,2,3,4,5',
                         help="Comma-separated unit sequence for Labouchere")
    betting.add_argument("--martingale-multiplier", type=float, default=2.0,
                         help="Bet growth factor on a loss for Martingale "
                              "(2.0 = classic double, 1.0 = no growth)")

    alin = p.add_argument_group("Alin Level strategy (only used with --strategy alin_level)")
    alin.add_argument("--alin-bets", default='1,6',
                      help="Comma-separated bet units per level (e.g. '1,6,20')")
    alin.add_argument("--alin-win-thresholds", default='1,1',
                      help="Comma-separated score target per level (>= wins the level)")
    alin.add_argument("--alin-loss-thresholds", default='-5,-5',
                      help="Comma-separated score floor per level (<= loses the level; must be negative)")
    alin.add_argument("--alin-win-behavior", choices=['step_back', 'reset'], default='step_back',
                      help="What happens on a WIN: 'step_back' (default) drops one level, "
                           "'reset' jumps straight back to Level 0")

    hilo = p.add_argument_group("Hi-Lo card counting (only used with --strategy hilo)")
    hilo.add_argument("--hilo-ramp", default='0:1,1:1,2:2,3:4,4:8,5:12,6:16',
                      help="Comma-separated 'TC:units' pairs, e.g. '0:1,1:1,2:2,3:4,4:8'")

    sim = p.add_argument_group("Simulation")
    sim.add_argument("--seed", type=int, default=None, help="Random seed (for reproducibility)")
    sim.add_argument("--verbose", action='store_true', help="Print per-round details")
    sim.add_argument("--print-every", type=int, default=1000, help="Verbose print frequency")
    sim.add_argument("--save-json", default=None, help="If set, save full game records to this JSON file")

    args = p.parse_args(argv)

    return Config(
        num_decks=args.num_decks,
        auto_shuffler=args.auto_shuffler,
        penetration=args.penetration,
        hit_soft_17=(args.soft_17 == 'hit'),
        max_split_hands=args.max_split_hands,
        double_after_split=(args.double_after_split == 'yes'),
        allow_surrender=args.surrender,
        blackjack_payout=args.blackjack_payout,
        num_games=args.num_games,
        base_bet=args.base_bet,
        max_bet=args.max_bet,
        betting_strategy=args.strategy,
        labouchere_sequence=args.labouchere_sequence,
        alin_bets=args.alin_bets,
        alin_win_thresholds=args.alin_win_thresholds,
        alin_loss_thresholds=args.alin_loss_thresholds,
        alin_win_behavior=args.alin_win_behavior,
        martingale_multiplier=args.martingale_multiplier,
        hilo_ramp=args.hilo_ramp,
        seed=args.seed,
        verbose=args.verbose,
        print_every=args.print_every,
        save_json=args.save_json,
    )


def main(argv: Optional[List[str]] = None) -> int:
    config = parse_args(argv)
    result = run_simulation(config)
    print(format_report(result))

    if config.save_json:
        with open(config.save_json, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'config': config.__dict__,
                    'summary': result.summary(),
                    'records': [r.__dict__ for r in result.records],
                },
                f,
                indent=2,
            )
        print(f"Full records saved to: {config.save_json}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
