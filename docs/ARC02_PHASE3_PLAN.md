# Phase 3 implementation plan

Baseline: 78 tests pass. Existing dirty Phase 2 work preserved on branch arc02-phase3-blueprint-authoring; baseline diff/status backed up under evidence/phase3-baseline. Use this branch in place because a clean worktree would omit the uncommitted required baseline.

1. Research native schemas and six pinned external implementations (complete).
2. Test structured specification, strict parser and deterministic code generation offline.
3. Implement isolated new-asset orchestration, journal and exclusive lock; no existing-asset mutation.
4. Verify real graph and native compile, save only after explicit compiler evidence; report unavailable status/reload as BLOCKED rather than guess.
5. Run full regression and bounded live tests, document evidence, review full diff.

Initial supported graph: one Actor EventGraph with BeginPlay and a linear sequence of PrintString calls. Variable declarations and data connections are reserved schema fields and fail closed until native semantics are verified. This is deliberately a partial implementation if those requirements remain unsupported.
