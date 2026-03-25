# Prompt Design Principles

Reference for designing VLM/LLM extraction prompts across this repo. Derived from the passport extraction prompt (98%+ accuracy on 66 cases).

## 1. Decompose into explicit steps

Force the model to work through stages instead of producing output in one shot. Each step narrows the task.

Our extraction uses 7 steps: image assessment → structured data → Arabic fields → MRZ → English fields → cross-validation → consistency check.

**Why it works:** The model commits to intermediate observations (orientation, quality, MRZ parse) before producing final values. Later steps can reference earlier ones. Errors are traceable to a specific step.

## 2. Separate sources, then cross-validate

Extract from each source independently first. Compare them in a dedicated step after.

We extract Arabic VIZ, English VIZ, and MRZ as separate steps, then cross-validate in step 6. The model never "blends" sources during extraction.

**Why it works:** Mixing sources during extraction causes silent contamination — the model reads a blurry Arabic name, then "confirms" it by transliterating from the English side. Separation prevents this.

## 3. Define signal priority

When sources disagree, the prompt must say which one wins and why.

- Dates: MRZ wins (machine-printed, check digit verified)
- Names: VIZ wins (MRZ truncates at 44 chars, drops diacritics)
- Passport number: MRZ wins (check digit)

**Why it works:** Without explicit priority, the model invents its own heuristic per-call, which is inconsistent.

## 4. State principles, not examples

Rules should describe *what to do*, not enumerate cases. Examples should illustrate the principle, not define it.

Bad: "عبدالله, عبدالرحمن, عبدالحكيم are each ONE token"
Good: "A name token is one unspaced word as printed. Read spacing from the image."

**Why it works:** Example lists cause overfitting. The model memorizes the examples and applies them even when wrong (e.g., "correcting" عبدالاله to عبدالله because it pattern-matched the examples). Principles generalize.

## 5. "Read what's there"

The prompt must block the model's instinct to infer, correct, or synthesize.

We repeat this in multiple forms:
- "Do NOT back-translate from English"
- "Do not invent or infer missing values — use null"
- "Read the Arabic characters directly from the image"
- "Do not apply merging or splitting rules"

**Why it works:** VLMs are trained to be helpful, which means they fill gaps. For extraction, gap-filling is hallucination. Explicit blocking reduces it — our runs show 0 hallucinations across 66 cases.

## 6. Assess the image before extracting

Step 1 forces the model to describe orientation, quality, mirroring, and skew before reading any fields.

**Why it works:**
- The model adjusts its reading strategy for rotated/mirrored images instead of failing silently.
- The metadata feeds the downstream programmatic confidence layer — no need to ask the model "how confident are you?"

## 7. Compute confidence programmatically

Never ask the model to self-report confidence. Compute it from observable signals.

We use: image metadata (mirroring → 0.35 cap, rotation → 0.7, poor quality → 0.65) + cross-validation warnings (check digit failure → 0.3, field mismatch → 0.2).

**Why it works:** LLM self-reported confidence has no calibration. Our experiment: model reported 0.99 on correct fields and 0.95 on wrong fields (useless 0.04 gap). Programmatic confidence: 0.98 correct vs 0.59 wrong (0.39 gap).

## 8. Structured reasoning trace, not free-text

The `_reasoning` output captures step 1 assessment, step 6 discrepancies, and step 7 consistency as structured fields — not a free-text chain of thought.

**Why it works:** Structured traces are parseable for debugging and monitoring. Free-text reasoning bloats output and is hard to use programmatically.

## Anti-patterns

- **Enumerating examples as rules** — causes overfitting to the examples
- **Asking "are you confident?"** — uncalibrated, wastes tokens
- **Mixing extraction with validation** — sources contaminate each other
- **One-shot extraction** — no intermediate reasoning, no traceability
- **Correcting extracted values in a later step** — step 7 flags inconsistencies but does not modify values
