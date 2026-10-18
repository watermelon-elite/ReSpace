# Issue tracker: GitHub

Issues and published specs live in GitHub Issues for
`watermelon-elite/ReSpace`. Use the `gh` CLI with
`--repo watermelon-elite/ReSpace`.

## Operations

- Create: `gh issue create --title "<title>" --body-file <file>`.
- Read: `gh issue view <number> --comments`.
- List: `gh issue list --state open --json number,title,body,labels`.
  Apply label/state filters as needed; fetch comments for selected issues.
- Update: `gh issue edit <number> --body-file <file>`.
- Comment: `gh issue comment <number> --body-file <file>`.
- Label: `gh issue edit <number> --add-label "<label>"`
  or `--remove-label "<label>"`.
- Close: `gh issue close <number>`.

Add the repository option to these commands. For multiline content,
write the exact text to a temporary file and pass it with `--body-file`.

Use `triage-labels.md` for the canonical label vocabulary.

## Skill conventions

“Publish to the issue tracker” means create a GitHub issue.
“Fetch the relevant ticket” means read the issue and its comments.
Return the verified issue URL after publication.

## Pull requests as a triage surface

PRs as a request surface: no.

## Wayfinding

Use one map issue labeled `wayfinder:map`, with child issues labeled
`wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`
or `wayfinder:task`.

Link children using GitHub sub-issues. If unavailable, maintain a task
list on the map and a `Part of #<map>` line on each child.

Represent blockers with native issue dependencies where available;
otherwise use `Blocked by: #<number>` lines. A child is actionable when
open, unassigned and free of open blockers. Choose in map order.

Claim by assigning the issue to the driving developer before work.
Resolve by recording the outcome, closing the child and adding a
concise result and link to the map's decisions.
