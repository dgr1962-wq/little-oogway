# Little Oogway Roundtable

Roundtable coordinates model participants through a deterministic, chaired deliberation and records every turn as JSONL.

The Open WebUI integration uses four stages:

1. **Opening statements:** every participant independently analyzes the agenda.
2. **Review:** every participant receives the shared opening docket and may record SUPPORT, OBJECTION, AMENDMENT, REQUEST FOR CLARIFICATION, POINT OF ORDER, or PASS.
3. **Procedural ledger:** the controller classifies each review's leading disposition without asking a model to infer it.
4. **Chair's disposition:** Little Oogway records the recommendation, agreements, dissent, unresolved questions, procedural rulings, and supported action owners. Unowned actions remain `UNASSIGNED`. `CONSENSUS` is allowed only when every rostered participant records `SUPPORT`; otherwise final minutes are `MIXED`.

This is a practical decision protocol rather than a strict implementation of Robert's Rules. It preserves dissent and does not invent votes or claim external actions occurred.

## Resumable procedure

The next procedure layer is implemented by `ResumableProcedure`. It keeps a
motion open when a review begins with `AMENDMENT`, `REQUEST FOR CLARIFICATION`,
`POINT OF ORDER`, or an unclassifiable response. The state is written beside
the append-only transcript, an operator can provide a ruling or missing fact,
and the same participants then perform another review pass without repeating
their opening statements.

Every pass receives its own mechanical ledger. External participants continue
to receive a withholding marker anywhere a local memory-informed Little Oogway
statement would otherwise enter their docket. `OBJECTION` records dissent but
does not itself prevent final minutes; unresolved procedural interventions do.

This layer is intentionally practical rather than a simulation of a legislature:
it adds motion continuity, operator rulings, repeat review passes, and honest
deferment while avoiding invented votes, quorums, seconds, or authorities.

Little Oogway's memory-informed opening remains private to the local chair. External participants receive the original agenda and one another's public openings, with the local opening replaced by a withholding marker. The chair receives the complete local docket and every external review.

The first working participant is Little Oogway through the local Ollama API. The older Selenium browser launcher remains in `controller.py` and `agents/` as legacy material; it is not part of the new controller yet.

## Run a local round

Create the local development environment once:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install wheel
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
```

Then run:

```bash
.venv/bin/oogway-roundtable \
  --with-mock \
  --prompt "What should Little Oogway contribute to the Roundtable first?"
```

The source-tree equivalent is:

```bash
PYTHONPATH=src python3 -m roundtable \
  --with-mock \
  --prompt "What should Little Oogway contribute to the Roundtable first?"
```

The command asks a deterministic mock participant and `qwen3:8b`, prints both replies, and writes a JSONL record under `transcripts/`.

Run only the deterministic participant without loading a model:

```bash
PYTHONPATH=src python3 -m roundtable \
  --mock-only \
  --prompt "Test the transcript pipeline."
```

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Current boundary

The controller provides participant abstraction, ordered opening and review
turns, failure isolation, Ollama integration, append-only transcripts, atomic
round state, operator rulings, and repeat review passes. The Open WebUI runtime
adds TokenSpace-aware Little Oogway plus visible ChatGPT and Claude participants
and the DeepSeek API monitor. Ordinary prompts create a no-contact preflight;
the operator must confirm its identifier before external participants are
contacted. Status inspection is local-only. A completed round cannot be resumed.
