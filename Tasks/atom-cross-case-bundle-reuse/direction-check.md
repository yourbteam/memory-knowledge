# Direction check — cross-case candidate bundle reuse

The recorded two-approach, two-case Development-Probe run retained four complete candidate
bundles although it contained only two unique candidate source identities. The immediate cause is
that the cross-case launcher fans out cases before the single-case launcher builds candidates; the
downstream all-probe collector then locates a separate case-local bundle even though it requires
one unchanged digest across all cases.

The current Development-Probe architecture remains sound: cases are isolated and rankings are
aggregated only after every case completes. The stable correction moves candidate construction to
the cross-case boundary, passes verified bundle identities into every single-case execution, and
gives each execution a disposable source materialization. Direct execution from one shared bundle
was rejected because a same-user candidate can change permissions and mutate shared evidence.

The contrary verdict would require evidence that candidate construction is case-dependent. Bundle
identity currently binds all declared case ids and no case bytes enter candidate construction.
