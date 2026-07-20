# Approval and Routing Contract

## Routing

Ordinary planning selects canonical `$plan-playbook`. The playbook performs planning only: it does not implement, review code, replace installed skills, commit, or push.

Direct invocation derives its deterministic task root. Task-workflow supplies its existing task root. Convergence supplies its live outer state and must already be in its authorized plan stage with matching objective, requirements, repositories, managed roots, and allowed paths.

## Planning-to-implementation boundary

A terminal planning PASS is not implementation permission. First emit and validate the current package, then create one package-bound implementation request from the exact `surface-map.json` approval payload.

The request presents:

- every granular change and its exact bounded paths;
- practical consequence as concrete `before` and `after` behavior;
- implementation and verification effort, complexity, and cost note;
- exact package, plan, requirement, scope, and manifest identities;
- one required confirmation bound to the request hash.

Any package revision, direct package edit, invalidation marker, scope drift, or request/evidence tamper invalidates implementation entry.

## Ordinary approval

For `approval_context=ORDINARY`, prepare the deterministic request once and enter `AWAITING_RESPONSE`. Present its exact content to the user. Accept only the exact required confirmation bytes through the controller. Denial or ambiguity leaves the same request pending and creates no authorization.

After exact approval, the controller writes immutable approval evidence and a canonical implementation authorization receipt. Restart reuses the same request or receipt. Write Code may start or resume only after both canonical `validate-package` and `validate-implementation-authorization` succeed.

## Convergence authorization

For `approval_context=CONVERGENCE`, controller initialization requires the live outer convergence state. The controller derives and snapshots an immutable authorization projection; a caller-authored enum or projection cannot suppress approval.

After package PASS, derive the same implementation request, then record authorization from the still-valid outer convergence envelope. Do not ask the user again. The resulting implementation receipt has the same package/scope/change/consequence/cost binding as ordinary approval, with convergence authorization as its source. A changed outer state or scope fails closed.

## G11 stop boundaries

Even after implementation authorization, stop for separate approval when evidence requires:

- a new requirement or materially wider plan;
- another repository, managed root, or allowed path;
- canonical promotion or installed canonical replacement;
- secret, credential, authentication, deployment, destructive, or external-message work;
- commit or push.

A material implementation-time plan change follows package invalidation and full re-hardening. Never patch the emitted package or treat prior approval as authority for the successor revision.

## Consumer rule

Task-workflow and convergence consume the canonical package exactly once through canonical owner boundaries. They do not independently rerun verify-plan, coverage, or satisfaction. Every implementation entry and resume revalidates both package and authorization receipt.
