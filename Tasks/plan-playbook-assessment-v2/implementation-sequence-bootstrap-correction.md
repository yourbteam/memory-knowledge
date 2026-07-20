# Planner V2 Implementation Sequence Bootstrap Correction

- Blocker: `blk-8deb7c7a317547bbc11745a0`
- Failed boundary: `scripts/discovery_bootstrap.py start`
- Failed inputs:
  - a partial-token path placeholder (`<run-directory>/score.json`);
  - a classification count based on implementation milestones rather than executable rows;
  - future evaluator commands whose executable did not yet exist and current executables absent from dependencies.
- Stable correction:
  - placeholders occupy a complete shell token;
  - `meaningful_steps` equals the number of executable rows in the initial spec;
  - the initial spec contains only currently executable commands;
  - every current executable is listed in the dependency manifest;
  - future evaluator commands are appended only after their approved executable exists.
- Same-path evidence: bootstrap returned `ok: true`, discovery
  `discovery-193fca0a-fee3-5854-900e-5047822fb419`, run
  `f85332ec-7f79-5d10-9792-f7a549c5d375`.
