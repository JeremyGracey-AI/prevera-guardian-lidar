# Room-frame plan: the adversarial reviews (2026-09-29)

Three reviews, each by a separate agent told to refute and not to approve, each read-only. The first two came
before the run and before the plan was pushed; the third read the results document and the edits that carry the
result into the README, the decision record, the architecture note and the development log. Every finding is
listed with what was done about it. Times are PDT.

## Review 1: the plan, runner, scorer and tests before the first commit (about 16:05)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | blocker | A failed request counted against R1 but for R2, so a server that stopped answering at frame 200 scored R1 PASS, R2 PASS with no walking frame answered | Any request error makes the run invalid: no verdict |
| 2 | blocker | The scorer gave a verdict on any frame count: a 3-frame file, a trimmed group and a camera spelled `C920` all scored PASS | The scorer checks 580 rows, no file twice, the fourteen declared groups with their declared counts |
| 3 | should-fix | A file from the other model, or at another confidence, got a verdict | Model, confidence and URL are checked against the declared values |
| 4 | should-fix | A non-JSON reply crashed the runner and lost every row | Any exception becomes an error row; the file is written in a `finally` block |
| 5 | should-fix | A second run silently replaced the first file | The runner refuses to write over a file |
| 6 | should-fix | "No prediction was written" was false: the two egress captures recorded the docker bridge, so the server's plaintext responses are inside the capture files | The plan says so, and that the payloads were not decoded |
| 7 | should-fix | "What a verdict means" could describe two cameras disagreeing as one behaviour; the near-duplicate finding was missing | Wording per camera; the near-duplicate and hips-and-legs findings added to the plan |
| 8 | should-fix | A class spelled `Lying` would read as `none` and record a false "measured no" | An unknown class name is a harness defect: invalid run, names listed |
| 9 | should-fix | 15 seeded mutations survived the tests | Tests rewritten; see `seeded_mutations.py` |
| 10 to 13 | notes | A 200 without `predictions` was not an error; the 09-27 verdict was computed under the per-segment reading; four smaller wording points; three code edges | All folded in |

Committed as `560006a` (16:14).

## Review 2: the same files at `560006a` (about 16:25)

The two blockers were closed; the reviewer found no way to get a wrong verdict from an honest, complete,
declared run.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | should-fix | `http_proxy` in the environment would send every request, frames and key, to another process, and the summary would still say loopback | The runner ignores proxy settings (`ProxyHandler({})`) |
| 2 | should-fix | `--limit 290` covered every counter-camera group, and the scorer printed the counts behind R1 and R2 before "INVALID", so the outcome could be known before a valid run existed | No smoke mode; the scorer prints no reading for an invalid run |
| 3 | should-fix | An output path under a missing directory was found out after all 580 requests, and nothing was written | The output file is created before the first request |
| 4 | should-fix | SIGTERM and SIGHUP (a dropped session) left no file; only Ctrl-C did | Both signals write the file with `complete` false |
| 5 | should-fix | Validity reads the runner's own record; a hand-typed file with the constants copied from the plan scored PASS | The plan says what the checks cannot show; the summary carries a digest of the rows and the scorer compares it; rows must carry the manifest's names in its order |
| 6 | should-fix | 6 of 15 new seeded mutations survived | Tests added; 44 mutants in all, none survives |
| 7 to 12 | notes | Unknown class name has no stated exit; the model-load sentence disagreed with the 09-28 results; two runs started together; a truncated file; serving is not a validity rule; loose equality | Exit stated (a new plan); wording fixed; exclusive create; unreadable file is an invalid run; by design, stated; typed comparison |

Committed as `2f39402` (16:51). Pushed, then the run.

## Review 3: the results document and the four carrying edits (about 17:25)

Every number in the results document reproduced from the raw file. The extract equals the scorer's output.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | blocker | README: "D 14 of 35 and E 22 of 33, the rest with no pose box" was wrong for D, which has 20 with no pose box and 1 `sitting` | Corrected |
| 2 | should-fix | Two documents asserted that the floor camera's failure "says the result depends on where the camera is", a cause the run cannot isolate (two camera models, heights and tilts differ at once) | Both sentences now say the result differs between the two cameras and why was not examined |
| 3 | should-fix | The README's opening paragraph stated the pass without the floor camera's failure, and read as one model passing both sets of bars | Rewritten: "from the counter camera only"; the floor camera's failure named; the two table rows name `00ba18` and `e65db0` |
| 4 | should-fix | "44 seeded mutations" had no artifact in the repository | `seeded_mutations.py` and its output committed beside this file |
| 5 | should-fix | Three sentences in `website/index.html` would contradict the repository once merged | Fixed on the website branch that follows this merge |
| notes | | "29 s after the push" treats an upper bound as the push time, and the two times come from two clocks | The results say "at least 29 s" and that the clock offset was not recorded |

## What the reviews did not examine

The images. The Jetson, GitHub or CI. Whether the 63 tests catch any mutation other than the 44 seeded ones.
