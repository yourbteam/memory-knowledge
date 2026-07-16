# Sequence Discovery Log: screenshot-page-source-locator
ReadyAtUtc: 2026-07-16T11:46:23Z

DiscoveryId: discovery-66c9c758-8b03-5e3b-9622-faa1044070c9
Status: promoted
PromotedSequenceId: screenshot-page-source-locator
CreatedAtUtc: 2026-07-16T10:52:32Z
RegisteredSequenceMatch: none

## Intended Outcome

Given a screenshot and candidate repository, identify the route, owning page/template, behavior script, styles, data boundary, duplicate variants, and confidence evidence without changing the target codebase.

## Why This Looks Repeatable

Screenshot-to-source tracing is a recurring multi-step investigation that must avoid false positives from shared labels, duplicate views, empty workspace roots, generated files, and dynamic data.

## Required Inputs, Auth, Or Environment


- A screenshot available to the agent for visual inspection.
- The intended repository root; if it is missing or empty, explicit user approval for any broader lookup.
- At least two stable UI labels or structural clues extracted from the screenshot, excluding dynamic or sensitive values.
- Optional current page URL, environment, branch, and reproduction path for resolving duplicate variants.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| trace-route-and-behavior | rg -n -e registrations-client-profile -e solutions-client-profile PSCMVC.Web/Controllers PSCMVC.Web/Auth PSCMVC.Web/wwwroot/templates PSCMVC.Web/Views | Confirmed two authorized routes, their controllers, left-menu links, Razor views, and page-specific scripts. | A matching view is only a candidate until its navigation and behavior chain are confirmed. |
| verify-automation | scripts/run_pytest.sh tests/test_screenshot_source_locator.py | passed: 4 tests | Exercises empty roots, candidate ranking, dependency/build exclusions, and the no-match fallback through the repository-mandated runner. |
| compare-duplicate-variants | diff -u PSCMVC.Web/Views/Registrations/RegistrationsClientProfile.cshtml PSCMVC.Web/Views/Solutions/SolutionsClientProfile.cshtml | Billing markup is shared; route-specific differences are the loaded script and Pricing fields, so the screenshot alone cannot distinguish the two routes. | Return bounded ambiguity with evidence instead of choosing a duplicate arbitrarily. |
| rank-stable-text | python3 scripts/screenshot_source_locator.py --repo /Users/kamenkamenov/CSS-FE-v2 --term Billing\ Information --term Payment\ Information --term Customer\ Type --term Client\ Profile --term Billing\ Info --term Pricing --format text | Ranked RegistrationsClientProfile.cshtml and SolutionsClientProfile.cshtml first with all six stable screenshot terms. | Use stable labels and structure; exclude customer names, card fragments, ids, and other dynamic values. |
| locate-confirmed-checkout | rg -l -i --glob !Library/** --glob !node_modules/** --glob !dist/** --glob !build/** Billing\ Information /Users/kamenkamenov | Located the exact labels under /Users/kamenkamenov/CSS-FE-v2 after the user authorized machine-level lookup. | Cross-root lookup requires explicit scope; never silently search outside the supplied repository. |
| validate-repository-root | find /Users/kamenkamenov/CSS-FE -maxdepth 3 -type f -not -path /Users/kamenkamenov/CSS-FE/.git/* -print | Requested root contained zero files and was not a Git checkout. | Stop before interpreting no text matches as page absence; confirm the actual checkout. |

## Failure Handling


If the repository is missing or empty, stop and confirm the real checkout. If exact stable text has no matches, inspect localization keys, route and menu concepts, runtime-provided labels, sibling packages within the approved scope, and generated sources. If several candidates render the same visible region, trace every route, controller, behavior script, style, and data boundary; report the remaining ambiguity and the missing discriminator such as URL or left-menu origin. Never use customer names, masked card values, profile ids, or other screenshot data as the only source locator.

## Verified Path


- On the supplied billing screenshot, the sequence rejected the empty CSS-FE root, located CSS-FE-v2 within the user-approved scope, ranked both six-label Razor candidates, traced their routes and scripts, and proved that the screenshot is shared by the Registrations and Solutions variants while the general Client Profile route lacks the visible Pricing tab.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
