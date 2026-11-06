# QA agents: real example runs

Each agent in `.claude/agents/` was run once on a real task in this repository.
The files below are the agents' actual output (only machine paths shortened), with a short note on the setup.

| # | Agent | Task | Result |
|---|---|---|---|
| 1 | [`test-case-designer`](01-test-case-designer.md) | New requirement: max pallet weight 1,000 kg | 31 test cases, 8 open questions; found a gap where blocked pallets can be moved out of NiO |
| 2 | [`test-code-reviewer`](02-test-code-reviewer.md) | Branch with 4 weak (but passing) tests | "Needs rework"; proved 3 tests could never fail by breaking the app on purpose |
| 3 | [`ci-failure-analyzer`](03-ci-failure-analyzer.md) | Red GitHub Actions run | CI showed 1 failure; agent found 3 from 2 causes, split product bug vs test bug, blocked the release, found a pipeline weakness |
| 4 | [`bug-report-writer`](04-bug-report-writer.md) | Product bug from the triage | Critical bug report; wider-impact check showed the no-short-allocation rule was silently bypassed |

**Pipeline improvement from the agents:** run 3 showed that a failing smoke gate left no report and crashed the summary step.
Fixed in commit `8a0e6c6`; [run 42292021037](https://github.com/Younus98/warehouse-automation-qa/actions/runs/42292021037) shows the fixed behaviour on the same broken branch.

The demo branches (`demo/weak-tests`, `demo/ci-red`) contained deliberate mistakes and are not part of `main`.
