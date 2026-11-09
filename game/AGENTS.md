# Game writing style

## Verification scope

Walker requested focused testing on 9 November 2026. Run checks needed for
the actual change and a short browser check for interaction fixes. Do not
rerun unrelated suites, balance simulations, renderer matrices or release
packaging for every source update. Expand checks only for a concrete risk,
failure or change to those components.

## Player-facing copy

Use casual, blunt language for player-facing flavor text. Prefer contractions
and natural phrasing over formal euphemisms. Non-graphic references to sex may
use words such as `fuck`, `pussy`, and `ass` where they fit the sentence; these
words do not need to be replaced with clinical vocabulary.

Keep descriptions non-graphic, vary the wording for repeated activities, and
state money, energy and other mechanical effects clearly. Keep the established
deterministic copy selection and automatic continuation after event choices.

If any requested wording cannot be included, tell the user exactly what is
blocked and confirm the alternative before implementing or pushing it.

## Deferred dialogue generation

Walker chose offline batch-generated message packs on 9 November 2026.
Revisit implementation near the final game revisions, once the dialogue
scenarios are settled. This is a development constraint to remember, not a
request to install a model or build the generator now.

- Generate many alternatives beforehand and import validated message packs.
  Gameplay should work with the model shut down and use no live generation.
- Walker writes and edits the model's generation instructions directly,
  including tone, style and wording. Provide that control when implementing;
  do not impose hidden writing instructions. The writing guidance above is
  for assistant-authored game text, not a mandatory generator prompt.
- The integration supplies scenario facts, supported conditions, fixed
  placeholders and the required output format. Keep writing separate from
  game rules, outcomes, money, energy, cards, saves and source code.
- Preserve compatibility with reusable message pools, recent-message
  tracking, existing fallback text and saved wording across reloads.
- Model selection, generation, message-pack import and story integration
  remain deferred. Keep these optional and independent of the main game.
