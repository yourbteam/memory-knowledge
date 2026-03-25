Execute an iterative review-fix-commit loop on recent work until convergence (no actionable findings remain) or the iteration cap is reached.

## WHAT THIS COMMAND DOES

You will perform up to 10 iterations of: review the accumulated commits, pass findings through a critic agent, implement actionable fixes, commit, and repeat. Each iteration compounds — the review scope grows to include all prior fix commits alongside the original work, so every cycle verifies both the original changes AND all corrections made so far.

**Convergence target:** The loop ends when the critic classifies all remaining findings as DISMISS or ACKNOWLEDGE (i.e., nothing left that warrants a fix now or in the future).

## SETUP

1. Identify the "base commit" — this is the commit just BEFORE the work being reviewed (i.e., the parent of the first commit in the work session). Use `git log` to find it.
2. All reviews will diff from that base commit to HEAD, so every iteration sees the full compounded picture.

## ITERATION PROTOCOL

For each iteration (starting at 1):

### Step 1: Quality Review (you perform this directly)

Run `git diff <base_commit>...HEAD` and `git log --oneline <base_commit>..HEAD` to see the full scope of accumulated changes.

Perform a thorough quality review covering:
- **Code correctness:** Logic errors, off-by-one, missing edge cases, type mismatches
- **Cross-file consistency:** Do changes across files work together? Are imports, registrations, and references aligned?
- **Plan alignment:** Do the changes match the plan/intent that was executed? Flag divergences.
- **Regressions:** Could any fix from a prior iteration have introduced new issues?
- **Completeness:** Are there gaps — missing tests, missing registrations, missing error handling?

Produce a structured findings list. Each finding MUST have:
- A specific file:line reference
- What is wrong (expected vs actual)
- Why it matters (impact)

**Do not produce vague or speculative findings.** If you cannot point to a specific line and explain the concrete problem, do not include it.

### Step 2: Critic Evaluation (delegate to a subagent)

Pass your findings to a critic subagent for validation. The critic applies 4 checks to each finding:

1. **Relevance** — Is it related to the work being reviewed, or tangential?
2. **Evidence** — Can the claim be verified against actual code? Is the reference correct?
3. **Impact** — Would ignoring it cause failures, bugs, or security issues? Or is it cosmetic?
4. **Actionability** — Is there a concrete fix within scope?

The critic categorizes each finding into one of four buckets:

| Bucket | Meaning | Action |
|--------|---------|--------|
| **FIX NOW** | Verified, high-impact, actionable | Implement this iteration |
| **IMPLEMENT LATER** | Valid but lower priority | Also implement this iteration (do not defer) |
| **ACKNOWLEDGE** | True observation but acceptable as-is | No action needed |
| **DISMISS** | False positive, irrelevant, or unverifiable | No action needed |

**Important:** Treat IMPLEMENT LATER the same as FIX NOW — implement both in this iteration. Only ACKNOWLEDGE and DISMISS are non-actionable.

### Step 3: Convergence Check

If the critic returned ONLY ACKNOWLEDGE and DISMISS findings (zero FIX NOW + zero IMPLEMENT LATER), the loop has converged. Report the final summary and stop.

If there ARE actionable findings (FIX NOW or IMPLEMENT LATER), proceed to Step 4.

### Step 4: Implement Fixes

For each actionable finding from the critic:
- Read the relevant file(s)
- Make the targeted fix
- Verify the fix doesn't break related code

**Rules:**
- Fix only what the critic validated — do not speculatively improve other code
- Keep fixes minimal and targeted
- Run tests if a test suite exists (`uv run pytest` or equivalent) to catch regressions

### Step 5: Commit and Continue

Commit the fixes with a message like: `fix: review iteration N — [brief summary of what was fixed]`

Log the iteration result:
```
--- Iteration N complete ---
Findings reviewed: X
FIX NOW: Y (implemented)
IMPLEMENT LATER: Z (implemented)
ACKNOWLEDGE: A (no action)
DISMISS: B (no action)
Commits in scope: [list of commit SHAs now covered]
```

Increment the iteration counter and return to Step 1. The next review will now cover the original work PLUS all fix commits — this is the compounding effect.

## ITERATION CAP

- **Primary cap:** 10 iterations.
- If after 10 iterations there are still actionable findings, present the remaining findings and ask: "There are still N actionable findings after 10 iterations. Should I continue for up to 10 more?"
- If the user approves, reset the counter and continue (same protocol).

## FINAL REPORT

When the loop ends (convergence or user stop), produce:

```
## Review-Fix Loop Summary

**Iterations completed:** N
**Total findings reviewed:** X
**Total fixes applied:** Y
**Convergence:** YES/NO (if NO, list remaining actionable findings)

### Iteration Log
| # | Findings | FIX NOW | IMPL LATER | ACK | DISMISS | Commit |
|---|----------|---------|------------|-----|---------|--------|
| 1 | ...      | ...     | ...        | ... | ...     | abc123 |
| 2 | ...      | ...     | ...        | ... | ...     | def456 |

### Remaining (if not converged)
1. [Finding description] — [why it wasn't fixed]
```

## CRITICAL RULES

1. **Findings must be grounded in actual code.** No hypothetical "this could be a problem" — point to specific lines.
2. **Each iteration reviews ALL accumulated commits**, not just the latest fix. This prevents fix oscillation.
3. **The critic is the authority on actionability.** Do not override its DISMISS/ACKNOWLEDGE decisions. Do not skip its FIX NOW/IMPLEMENT LATER decisions.
4. **Do not gold-plate.** The goal is correctness and completeness of the reviewed work, not general codebase improvement. Stay within the scope of the commits being reviewed.
5. **Commit after every fix iteration.** This creates a clear audit trail and ensures the next review sees the fixes.