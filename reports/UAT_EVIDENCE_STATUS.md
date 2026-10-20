# CashBridge v9 | Real User Testing Evidence Status

**Status as of 20 October 2026:** The team has explicitly stated that user testing **was conducted**. The original v9 source archive does **not** contain individual participant records or an aggregated user-testing outcome. The team statement is preserved, while numerical outcomes remain **unverified from the submitted ZIP**.

This is **not** a finding that no testing happened. It is an evidence-packaging gap.

## 1. What can be stated safely now

- The team confirms it completed user testing.
- An independent user-test protocol exists at `docs/UAT_PROTOCOL.md`, covering accountant, director and lender reviewer scenarios.
- Browser automation also covers multi-role, mobile and multilingual workflows; those automated checks are *not* substitutes for real users.
- **Do not assert** a participant count, completion rate, median time, SEQ, SUS, critical-error rate or improvements discovered until supporting notes/records have been shared.

## 2. Actual UAT evidence needed to fill the final report

| Field | Current archived value | What to attach |
|---|---|---|
| User-test dates | Not provided | Actual date(s) and product version/URL tested |
| Recruitment / user roles | Not provided | Counts by accountant, director and lender role; whether independent of team |
| Method | Not provided | Guided or unassisted, remote/on-site, language and device |
| Tasks | Not provided | Which A1–A5, D1–D3, B1–B4 tasks were *actually* observed |
| Success/critical error | Not provided | Per-participant actual result, including failures and assisted steps |
| Time/errors/SEQ | Not provided | Record only if genuinely measured; do not impute missing values |
| SUS | Not provided | Ten answers (1–5) if administered; otherwise report `not measured` |
| Findings and fixes | Not provided | Exact usability issues, shipped changes, test version for follow-up |
| Recording and consent | Not provided | Consent status and de-identified file names/links, no personal details in public ZIP |

## 3. Recommended summary for the final evidence pack (replace placeholders **only with real data**)

**Participant pool:** `[number verified]` people (`[n]` accountant, `[n]` director, `[n]` lender), tested `[date/version]`, `[guided/independent]`.  
**Observed tasks:** `[task IDs actually tested]`.  
**Unaided completion:** `[successful attempts]/[all observed task attempts]` = `[calculated percentage]`.  
**Critical errors:** `[observed count]`.  
**Ease:** median SEQ `[actual value]/7` *or* `not measured`.  
**SUS:** `[actual value]/100` *or* `not measured`.  
**Changes made after UAT:** `[what was changed and linked commit/screenshot, or no changes]`.  
**Evidence:** `[anonymised notes, recordings if consented, CSV, report]`.

These are **deliberately unfilled variables**, not numbers to copy into a deck.

## 4. Import into the existing UAT reporter, when the protocol was followed

Use `reports/uat_results_TEMPLATE.csv` as header and enter one **actual** participant-task observation per line in `reports/uat_results.csv`. The existing `eval/uat_summary.py` expects the specified numeric columns including SEQ/SUS; if these were not recorded in the real testing, **do not make up answers to satisfy the parser**. Instead preserve the original notes and summarise observed metrics manually with the same clear numerator/denominator and a `not measured` label.

```bash
python eval/uat_summary.py reports/uat_results.csv
# Creates reports/uat_summary.md only when complete, correctly formatted records exist.
```

**Internal acceptance thresholds** from `docs/UAT_PROTOCOL.md` (not official organiser rules): per-task 80% unaided, 0 critical errors, median SEQ >=5/7, mean SUS >=68 by role. A small participant sample creates uncertainty. Publish failed tasks rather than hiding them.

## 5. Optional raw-note mapping

| Test/session ID (pseudonym) | Role | Tasks actually attempted | Completed unaided | Serious difficulty / error | User quote (consented) | Resolution |
|---|---|---|---|---|---|---|
| `[S01]` | `[actual]` | `[actual]` | `[actual]` | `[actual]` | `[actual or not recorded]` | `[fix / open]` |

**Integrity statement:** This file makes no claim of numeric UAT results. The user's confirmation that the team conducted UAT is treated as a team statement; objective evidence is pending inclusion in the submitted source archive.
