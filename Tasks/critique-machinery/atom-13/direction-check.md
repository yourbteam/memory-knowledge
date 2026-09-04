# Direction check — validation declarations

The same failure class occurred three times: a rule treated free text as structured data and the
next regeneration exposed another parser exception. Two paths were weighed against the recorded
runs.

1. **True defects on a sound parser approach.** Keep adding parser corrections. This repaired each
   observed sentence but left the distance to the goal unchanged: the next atom author could still
   introduce another prose-reading validation with no declaration or owner decision.
2. **The approach cannot reach the goal.** Move the decision boundary to atom start. Require every
   validation target and its schema shape before the experiment can run; prose requires Kamen's
   explicit waiver. This makes the unknown future set inspectable without reverting any existing
   live fix.

The evidence supports path 2. The deciding fact is recurrence across three different rules and
honest texts after each prior parser repair. The verdict would flip only if the atom request could
not identify the validation target before implementation; all four frozen requests already make
that target explicit in their recorded outcomes and candidate modules.
