# Golden scenario results

These transactional, rollback-only checks were run against the locally loaded Missouri S&T FA26 snapshot on 2026-08-14. Each recommended solve used a 60-second hard wall-clock budget. Credits below are degree-applicable future credits; all scenarios began in Fall 2026 with an 18-credit regular-term cap and the published major minimum enabled.

## Summary

| Scenario | Candidates | Assignment variables | Solve time | Result | Graduation | Future credits | Additional credits | Max term credits | Credit spread | Max high-level courses/term | Summer credits | Legitimate shared credits |
| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aerospace Engineering BS, no summer | 1,114 | 12,736 | 41.197s | OPTIMAL | Spring 2030 | 128 | n/a | 16 | 0 | 3 | 0 | 0 |
| Computer Science BS + AI Emphasis | 1,784 | 14,621 | 60.076s | Last proven optimum retained; deadline reached | Fall 2031 | 127 | unavailable after deadline | 18 | 17 | 4 | 8 | 0 |
| IST BS only, balance then earliest | 1,065 | 9,094 | 50.320s | OPTIMAL | Spring 2031 | 120 | n/a | 9 | 3 | 1 | 31 | 0 |
| IST BS + AI/ML minor, fewest credits | 1,066 | 9,099 | 29.145s | OPTIMAL | Fall 2031 | 120 | 0 | 18 | 15 | 4 | 14 | 15 |
| IST BS + AI/ML minor, overlap then balance | 1,066 | 9,099 | 56.408s | OPTIMAL | Fall 2031 | 120 | 0 | 9 | 6 | 1 | 27 | 15 |
| IST BS + AI/ML minor, balance then overlap | 1,066 | 9,099 | 47.858s | OPTIMAL | Fall 2031 | 120 | 0 | 9 | 6 | 1 | 31 | 15 |

“Credit spread” is the difference between the largest and smallest used-term credit loads. “High-level” means 4000/5000-level and is a transparent course-level distribution proxy, not a difficulty estimate.

## Scenario A — Aerospace Engineering BS

The plan proved every optimization stage optimal: minimum future credits, minimum course count, earliest graduation, balanced workload, avoidance of unnecessary early 5000-level work, and academic-quality tie-breakers. It schedules 45 courses totaling the published 128 credits, uses eight 16-credit Fall/Spring terms, and uses no summer. No unresolved `CREDIT_REQUIREMENT`, omitted prerequisite-course, duplicate-credit, or overlap-policy condition was found.

The catalog contains 262 consent/exam/other unstructured prerequisite leaves relevant to this candidate universe. They remain informational advisor-verification conditions rather than invented machine constraints.

## Scenario B — Computer Science BS + Artificial Intelligence Emphasis

The compatible CS/AI relationship is accepted; the inverse test with Aerospace as the only selected major is rejected by backend validation. The solve proved minimum credits, minimum course count, and actual overlap optimal before the 60-second deadline stopped the next earliest-graduation stage. The prior valid plan was retained and the deadline condition was surfaced rather than extending the budget.

The result reports **zero** cross-program shared credits because requirement sets inherited from the parent CS major are intentionally excluded from emphasis-overlap scoring. It does not mislabel the 127-credit base degree as AI-emphasis overlap. There are 373 unstructured prerequisite conditions for advisor verification. The prototype also emits the cross-program policy warning because the source snapshot has no explicit policy for this pairing.

## Scenario C — IST BS + AI/ML in Business Minor

The primary-only baseline requires 120 future degree-applicable credits. Every combined-program variant also requires 120, so the measured additional-program delta is zero: the minor is completed through legitimate reuse rather than extra padding.

The fewest-credit result shares 15 actual allocated credits across the selected programs: `STAT 1115`, `IS&T 3333`, `IS&T 3420`, `IS&T 5520`, and `BUS 5730`. The overlap-first and balance-first variants also share 15 allocated credits, using `IS&T 3343`, `IS&T 3420`, `IS&T 5420`, `IS&T 5520`, and `BUS 5730`. Their different priority orders preserve the same minimum total and shared-credit optimum; the balance stage reduces the worst term from 18 credits/four high-level courses to 9 credits/one high-level course.

All variants retain 251 unstructured prerequisite conditions as advisor-verification information and disclose that cross-program double-counting policy is not present in the source data. A rollback-only edit exercise added unrelated `CHEM 1001`, increasing scheduled workload from 120 to 123 while degree-applicable progress remained 120; moving it between two valid existing terms succeeded, removing it succeeded, and removing a necessary planned course was rejected for breaking a downstream prerequisite. The exact minimum-credit golden plan exposed no validator-approved replacement for its shared allocations, so no shared swap was offered. Dedicated transactional fixtures separately verify a valid shared/group alternative swap, unrelated-swap rejection, dependent-prerequisite rejection, mandatory-course removal rejection, reallocation, and status/metric recomputation.

## Regression interpretation

Candidate and assignment-variable counts should remain near these values unless catalog scope or safe pruning changes. A material increase in total credits, inherited emphasis “overlap,” early high-level clustering under the balance objective, or wall time beyond the configured deadline is a regression signal. Exact course placement can vary with OR-Tools search behavior while all locked objective values remain equal.
