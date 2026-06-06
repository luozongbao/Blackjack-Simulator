# 🎰 Blackjack Monte Carlo Simulator

A flexible, fast Blackjack simulator with configurable rules, multiple betting
strategies, basic-strategy play, and detailed session reports. Written in
pure Python with no external dependencies.

Supports **flat betting**, **classic progressions** (Martingale, D'Alembert,
Oscar's Grind, Fibonacci, Labouchere), **stateful mini-game progressions**
(Alin Level), and **card counting** (Hi-Lo with a configurable bet ramp).

## ✨ Features

- 🃏 **Configurable rules** — soft 17, deck count, auto-shuffler, split limits,
  double-after-split, surrender, blackjack payout, penetration
- 🎯 **Basic Strategy** built in (S17 standard)
- 💰 **7+ betting strategies** (see [Betting strategies](#-betting-strategies))
- 📊 **Card counting** — Hi-Lo running count with true-count bet ramp
- 📈 **Detailed reports** — win/lose/push, EV, drawdown, equity curve, plus
  strategy-specific aggregates (e.g. Alin Level max level, Hi-Lo true count range)
- 🔁 **Reproducible** — `--seed` produces bit-identical runs
- 💾 **Optional JSON export** of every round for post-hoc analysis
- ⚡ **Pure standard library** — no `numpy`, no `pandas`, no installs

## 🚀 Quick start

```bash
# Run with defaults (10,000 games, 6 decks, flat bet, S17)
python blackjack_simulator.py

# 50,000 games with Martingale and a bet cap
python blackjack_simulator.py --num-games 50000 --strategy martingale --max-bet 5000

# 100,000 games with Hi-Lo card counting + deep penetration
python blackjack_simulator.py --num-games 100000 --strategy hilo --penetration 0.9

# See all options
python blackjack_simulator.py --help
```

## 🛠 Installation

Requires **Python 3.10+** (uses `from __future__ import annotations` and modern
type hints). No third-party packages.

```bash
git clone https://github.com/<your-username>/Blackjack-Simulator.git
cd Blackjack-Simulator
python blackjack_simulator.py --help
```

If `python` isn't on your `PATH` (common on Windows after a manual install),
point directly at the binary, e.g.:

```bash
"C:\Users\<you>\AppData\Local\Programs\Python\Python314\python.exe" blackjack_simulator.py
```

## ⚙️ Configuration

Every rule and parameter is exposed as a CLI flag. Defaults match common
single-deck / multi-deck casino rules.

### 🃏 Rules

| Flag | Default | Description |
|------|---------|-------------|
| `--soft-17 {hit,stand}` | `stand` | Dealer action on soft 17 |
| `--num-decks N` | `6` | Decks in the shoe |
| `--auto-shuffler` | off | Reshuffle every round |
| `--penetration FLOAT` | `0.75` | Reshuffle when this fraction of the shoe is dealt |
| `--max-split-hands N` | `4` | Max player hands after splits |
| `--double-after-split {yes,no}` | `yes` | Allow DAS |
| `--surrender` | off | Allow late surrender |
| `--blackjack-payout FLOAT` | `1.5` | BJ payout (3:2 = 1.5) |

### 💵 Betting

| Flag | Default | Description |
|------|---------|-------------|
| `--num-games N` | `10000` | Rounds to simulate |
| `--base-bet FLOAT` | `10.0` | Base bet unit |
| `--max-bet FLOAT` | `10000.0` | Bet cap (for progressions) |
| `--strategy STRATEGY` | `flatbet` | See [strategies](#-betting-strategies) |

### 🔬 Simulation

| Flag | Default | Description |
|------|---------|-------------|
| `--seed N` | random | Seed for reproducibility |
| `--verbose` | off | Print per-round details |
| `--print-every N` | `1000` | Verbose print frequency |
| `--save-json PATH` | none | Save all records to JSON |

## 💸 Betting strategies

| Key | Strategy | Notes |
|-----|----------|-------|
| `flatbet` | Flat Bet | Always `base_bet` |
| `martingale` | Martingale | Multiply by `--martingale-multiplier` (default 2.0) on loss, reset on win |
| `reverse_martingale` | Reverse Martingale / Paroli | Multiply by `--martingale-multiplier` (default 2.0) on win, reset on loss |
| `dalembert` | D'Alembert | +1 unit on loss, −1 on win |
| `unit_progression`, `plus_minus` | _aliases of D'Alembert_ | more descriptive names |
| `oscars_grind` | Oscar's Grind | Win 1 unit per cycle, grow on wins |
| `fibonacci` | Fibonacci | Step up the sequence on loss, down 2 on win |
| `labouchere` | Labouchere / Cancellation | Sequence-based, see `--labouchere-sequence` |
| `alin_level` | Alin Level | Custom mini-game with per-level score thresholds; WIN behavior is `step_back` (default) or `reset` |
| `hilo` | Hi-Lo Card Counting | True-count bet ramp, see `--hilo-ramp` |

### Martingale multiplier

The `--martingale-multiplier` flag (default `2.0`) controls the bet growth
factor for both `martingale` and `reverse_martingale` — on a loss in the
former, on a win in the latter.

| Value | martingale (loss) | reverse_martingale (win) |
|-------|-------------------|---------------------------|
| `1.0` | No growth — effectively flat betting | No growth — effectively flat betting |
| `1.5` | Gentler loss-recovery | Slower winnings compounding |
| `2.0` (default) | Classic "double on loss" | Classic Paroli "double on win" |
| `3.0` | Aggressive loss-recovery | Aggressive winnings compounding |
| `5.0+` | Extreme (mostly stress-tests) | Extreme (mostly stress-tests) |

```bash
# Default (classic)
python blackjack_simulator.py --strategy martingale
python blackjack_simulator.py --strategy reverse_martingale

# Gentler progression
python blackjack_simulator.py --strategy martingale          --martingale-multiplier 1.5
python blackjack_simulator.py --strategy reverse_martingale  --martingale-multiplier 1.5

# Aggressive
python blackjack_simulator.py --strategy martingale          --martingale-multiplier 3.0
```

The bet is always capped at `--max-bet`. Values `<= 0` are rejected by the
strategy constructor with `ValueError`.

### Alin Level — custom mini-game progression

Each level has a bet size and two score thresholds. The session starts at
level 0 with score 0; after each round, score moves `+1` on net win, `−1` on
net loss. Hitting the **win threshold** resets to level 0 (mini-game win).
Hitting the **loss threshold** either advances to the next level or, if there
is none, resets to level 0 (mini-game loss).

```bash
# Default 2-level config: (1u, +1, -5), (6u, +1, -5)
python blackjack_simulator.py --strategy alin_level

# Custom 3-level
python blackjack_simulator.py --strategy alin_level \
    --alin-bets "1,4,15" \
    --alin-win-thresholds "1,2,1" \
    --alin-loss-thresholds "-3,-4,-5"
```

The default 2-level scheme is exactly: Level 0 bet 1u (need +1 to win, lose at −5 → advance
to Level 1); Level 1 bet 6u (need +1 to win, lose at −5 → reset to Level 0).

#### WIN behavior (`--alin-win-behavior`)

When the score hits the **win** threshold, you can choose what happens to the
level index. Both modes share the same `level_wins` metric, which only counts
WINS that happen **at Level 0** (a fully completed mini-game).

| Mode | What a WIN does | Example (3 levels) |
|------|-----------------|---------------------|
| `step_back` (default) | Drop one level (clamped at 0) | WIN at L2 → L1; WIN at L1 → L0; WIN at L0 → L0 |
| `reset` | Jump straight back to Level 0 | WIN at L2 → L0; WIN at L1 → L0; WIN at L0 → L0 |

`level_step_backs` tracks WINs that happened at Level ≥ 1 (with `step_back`,
this is the count of times you dropped a level; with `reset`, this is the
count of non-L0 wins that nonetheless snapped the index back to 0).

```bash
# Default: step back one level on win
python blackjack_simulator.py --strategy alin_level

# Legacy behavior: any win resets to Level 0
python blackjack_simulator.py --strategy alin_level --alin-win-behavior reset
```

> 💡 With only 2 levels the two modes are observationally equivalent (a WIN
> at Level 1 lands at Level 0 either way). To see the difference, use 3+
> levels.

### Hi-Lo card counting

The deck tracks a running Hi-Lo count: 2-6 = +1, 7-9 = 0, 10/J/Q/K/A = −1. The
strategy computes the **true count** (`running_count / decks_remaining`) and
scales the bet by a ramp. Default ramp is Wong's standard 1-1-2-4-8-12-16.

```bash
# Default Wong spread
python blackjack_simulator.py --strategy hilo --penetration 0.9

# Custom aggressive spread
python blackjack_simulator.py --strategy hilo \
    --hilo-ramp "0:1,1:1,2:2,3:4,4:8,5:16,6:32" \
    --max-bet 5000
```

> 💡 Counting only works when the shoe isn't reshuffled every round. Use
> `--penetration 0.85+` for realistic edge. With `--auto-shuffler`, the count
> resets every round and produces zero edge.

## 📊 Sample report

```
================================================================
BLACKJACK SIMULATION -- REPORT
================================================================
Customization (config):
  Number of decks        : 6
  Soft 17                : Stand
  Max split hands        : 4
  Double after split     : Yes
  Blackjack payout       : 1.5:1
  Betting strategy       : hilo
  Number of games        : 500000

================================================================
PROFIT & LOSS
================================================================
  Total won              :   5453040.00
  Total lost             :   5377220.00
  Total net payout       :    +75820.00
  EV per hand            :      +0.1516
  EV per unit bet        :    +0.007245
  Expected value (EV)    :      +0.1516

================================================================
EQUITY
================================================================
  Starting equity        :        +0.00
  Final equity           :    +75820.00
  Min equity             :   -11980.00
  Max equity             :    +87840.00
  Max drawdown           :     17940.00

================================================================
STRATEGY STATE
================================================================
  avg_true_count         : -0.04
  max_true_count         : 27.37
  min_true_count         : -27.62
  top_bet_rounds         : 0
```

For Alin Level, `STRATEGY STATE` shows:

```
  current_level          : 0
  current_score          : 0
  max_level_reached      : 2
  win_behavior           : step_back
  level_wins             : 8525   # WINs at Level 0 (mini-game completed)
  level_step_backs       : 4698   # WINs at higher levels
  level_losses           : 6060
```

## 🧠 Basic strategy

The player follows **S17 standard basic strategy** (Wizards of Odds charts) for
hard totals, soft totals, and pairs. Surrender deviations (15 vs 10, 16 vs 9/10/A)
are included when `--surrender` is enabled.

The strategy makes these decisions per hand:

- `H` Hit, `S` Stand, `D` Double (else Hit if not allowed),
  `P` Split, `R` Surrender

The Hi-Lo strategy does **not** modify play decisions — only bet sizing.

## 📁 Project structure

```
Blackjack-Simulator/
├── blackjack_simulator.py   # All code in one file (≈1,000 lines)
├── README.md                # This file
└── results.json             # (optional) --save-json output
```

```
blackjack_simulator.py
├── Card, Deck, Hand
│   └── Deck.running_count updated on every deal, reset on shuffle
├── Basic Strategy tables (HARD_S17, SOFT_S17, PAIRS)
├── BettingStrategy base + 7 strategies + Alin Level + Hi-Lo
├── Config, Game, SimulationResult, run_simulation
├── _parse_alin_levels, _parse_hilo_ramp  (CLI helpers)
├── _attach_dash_values  (argparse quirk workaround)
└── format_report
```

## 🔬 Validating results

A 100k-game flatbet run on default S17 6-deck rules produces EV/hand ≈
−0.04 (house edge ≈ −0.4%), in line with published basic-strategy numbers
(Wizards of Odds, etc.). A 500k Hi-Lo run with `--penetration 0.9` produces
EV per unit bet ≈ +0.7%, the expected player edge for a 1-16 spread.

## 🧪 Reproducibility

```bash
$ python blackjack_simulator.py --num-games 2000 --seed 42 --strategy hilo
... Final equity : +380.00
... max_level    : 2

$ python blackjack_simulator.py --num-games 2000 --seed 42 --strategy hilo
... Final equity : +380.00  # identical
... max_level    : 2
```

## 🤝 Contributing

Ideas welcome — open an issue or PR. Easy extensions:

- More betting strategies (1-3-2-6, Contra D'Alembert, Kelly Criterion)
- More count systems (Hi-Opt I/II, KO, Omega II)
- Wonging (sit-out when count is low)
- Per-round `current_level` / `current_score` / `current_tc` in the JSON dump
  for richer post-hoc analysis
- Plotting (equity curve histogram, TC distribution) — needs `matplotlib`

## 📜 License

MIT — do what you want, no warranty. See [LICENSE](LICENSE) if present.

## ⚠️ Disclaimer

This is a statistical simulation for educational purposes. It is not
financial advice, and it is not a tool for winning money. The house edge
is real — even a perfect counter is fighting variance, casino heat, and
rule variation. Don't gamble with money you can't afford to lose.
