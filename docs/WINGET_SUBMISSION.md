# winget Submission

How the winget manifest gets published, why the previous automation was
replaced, and what to do when it breaks.

## How it works now

The `publish-winget` job in `.github/workflows/build-all.yml` runs on tags and
does two separable things:

1. **komac generates the manifests** — `komac update <id> --version <v> --urls
   <exe> --dry-run --output ./wg`. This computes the installer SHA256, detects
   the installer type, and inherits fields from the previous version. It writes
   the real winget tree, e.g.
   `wg/manifests/a/aahepburn/RAGAssistantForZotero/0.5.2/`.
2. **`gh` submits the PR** — syncs the fork, recreates the branch, commits the
   files komac produced, and opens the PR against `microsoft/winget-pkgs`.

The split matters. Manifest generation has never been the failing part; the git
side has. Keeping them separate means a submission failure can be redone by hand
in about a minute without re-deriving anything (see **Manual submission**).

Relevant facts:

| Thing | Value |
|---|---|
| Package identifier | `aahepburn.RAGAssistantForZotero` |
| Fork | `aahepburn/winget-pkgs` (owned by the user, **not** the org) |
| Manifest path | `manifests/a/aahepburn/RAGAssistantForZotero/<version>/` |
| Secret | `WINGET_TOKEN` — classic PAT on the `aahepburn` account |

The token has to belong to `aahepburn` because the fork does. `GITHUB_TOKEN`
cannot be used: it is scoped to this repository and cannot write to the fork.

## Root cause found (2026-10-10)

The v0.6.0 release failed at the first `gh` call, the fork sync, with a message
that names the cause:

```
gh: refusing to allow a Personal Access Token to create or update workflow
`.github/workflows/domain-validation-assist.lock.yml` without `workflow` scope (HTTP 422)
```

`microsoft/winget-pkgs` changes files under `.github/workflows/`. GitHub refuses
to let a personal access token write workflow files without the `workflow`
scope, and that includes copying upstream's workflow changes into the fork,
whether by syncing it or by creating a branch at an upstream commit. The
`WINGET_TOKEN` has `public_repo` (later `repo`) but not `workflow`.

This almost certainly explains the 2026-09-09 `CreateRef` failure below: the
action created its branch from upstream's head, which carried workflow changes
the fork did not have. It fits every item in the "ruled out" table, including why
`repo` did not help (it is a separate scope) and why the same token could create
a ref at the fork's own head (HTTP 201). It also explains why both manual
submissions worked: they ran under the maintainer's `gh` login, which has
`workflow`.

**Fix:** give `WINGET_TOKEN` the `workflow` scope (classic PAT: `public_repo` +
`workflow`). Until then, submit by hand as below; v0.6.0 was submitted that way
in [PR 450264](https://github.com/microsoft/winget-pkgs/pull/450264).

## The 2026-09-09 failure (now explained above)

During the v0.5.2 release, `publish-winget` failed three times with:

```
0: aahepburn does not have the correct permissions to execute `CreateRef`
1: failed to create branch aahepburn.RAGAssistantForZotero-0.5.2-<uuid>
```

**The root cause was never found.** The job was using
`vedantmgoyal9/winget-releaser@v2`, which wraps komac and does its own git work.
It was replaced with the komac + `gh` split described above, which routes around
the failure rather than explaining it. Record this honestly: if the same symptom
appears elsewhere, nothing below tells you why.

### Ruled out, with evidence

Do not re-investigate these without new information.

| Hypothesis | Evidence against |
|---|---|
| Token expired | Classic PAT, `public_repo`, expiry 2027-07-28 |
| Token cannot write to the fork | Same token created a ref over REST: **HTTP 201** |
| GraphQL mutations need `repo` scope | Regenerated with `repo`; still failed |
| Secret not updated before the re-run | Secret updated 21:26:33, attempt 3 started 21:28:01 |
| Secret empty or unset | Log shows `token: ***` and `GITHUB_TOKEN: ***` on the komac step |
| Action or komac version drift | Both runs: action SHA `4ffc7888`, komac `v2.16.0` |
| Fork deleted, renamed or archived | Exists since 2026-03-22, `archived=false`, `KOMAC_FORK_OWNER: aahepburn` |
| Leftover branch blocking the ref | No branch with that name existed |

The v0.5.1 release (run `30454093046`, 2026-07-29) succeeded with a byte-identical
action SHA and komac version.

### Loose ends

- **Whose identity is `aahepburn` in the error?** Unknown. It may be the
  authenticated user, or komac echoing the `KOMAC_FORK_OWNER` input. Every
  hypothesis above assumed the former. If it is the latter, the identity being
  denied could be something else entirely and the investigation was built on
  sand. **Check this first if the symptom returns.**
- **The PAT showed "Never used"** in the account's token list despite the
  successful July release. Either GitHub's last-used tracking has a gap (it is
  known not to reflect all API traffic), or the secret held a different token
  than the one being inspected. Never resolved.
- **The fork was 18,492 commits behind** upstream at the time. Not plausibly
  causal — a bad base SHA returns 422, not a permissions error — but it was true,
  and it is now synced on every run.

## Diagnosing a failure

```bash
RUN=<run-id>   # from: gh run list --workflow build-all.yml

# Job state (job IDs change on every re-run attempt)
gh run view $RUN --repo Quiet-Signals-Lab/RAG-Assistant-for-Zotero \
  --json jobs -q '.jobs[] | "\(.name) :: \(.conclusion) \(.databaseId)"'

# Full log for the winget job
gh api repos/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions/jobs/<job-id>/logs

# Was the secret actually updated before the attempt ran?
gh api repos/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions/secrets \
  -q '.secrets[] | select(.name=="WINGET_TOKEN") | .updated_at'
gh api repos/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/actions/runs/$RUN/attempts/<n> \
  -q .run_started_at
```

To test whether `WINGET_TOKEN` can do the operation that failed, paste it at the
prompt (leading space keeps the command out of shell history):

```bash
 read -rs TOK
 curl -s -w '\nHTTP %{http_code}\n' -X POST \
   -H "Authorization: Bearer $TOK" \
   https://api.github.com/repos/aahepburn/winget-pkgs/git/refs \
   -d '{"ref":"refs/heads/perm-test","sha":"<current fork master sha>"}'
 # 201 = the token is fine, look elsewhere
 # 403 = genuinely lacks write   401 = expired, revoked or malformed
 curl -s -X DELETE -H "Authorization: Bearer $TOK" \
   https://api.github.com/repos/aahepburn/winget-pkgs/git/refs/heads/perm-test
 unset TOK
```

Note that a bare `$WINGET_TOKEN` in your local shell is **empty** — the secret
only exists inside Actions. An empty bearer returns 401 and looks exactly like an
expired token. This wasted time during the original investigation.

## Manual submission

If the job fails and the release is otherwise fine, submit by hand. The release
itself does not need to be re-cut and the tag does not need to move.

```bash
VERSION=0.5.2
PKG_ID=aahepburn.RAGAssistantForZotero
URL=$(gh release view "v$VERSION" --repo Quiet-Signals-Lab/RAG-Assistant-for-Zotero \
        --json assets --jq '.assets[] | select(.name|test("\\.exe$")) | .url' | head -1)

# 1. Generate (komac binary: https://github.com/russellbanks/Komac/releases)
GITHUB_TOKEN=$(gh auth token) komac update "$PKG_ID" --version "$VERSION" \
  --urls "$URL" --dry-run --output ./wg

# 2. Sync the fork and branch
gh api -X POST repos/aahepburn/winget-pkgs/merge-upstream -f branch=master
BASE=$(gh api repos/aahepburn/winget-pkgs/commits/master -q .sha)
gh api -X POST repos/aahepburn/winget-pkgs/git/refs \
  -f ref="refs/heads/$PKG_ID-$VERSION" -f sha="$BASE"

# 3. Commit each manifest at the path komac produced
for f in $(cd wg && find manifests -name '*.yaml'); do
  gh api -X PUT "repos/aahepburn/winget-pkgs/contents/$f" \
    -f message="New version: $PKG_ID version $VERSION" \
    -f branch="$PKG_ID-$VERSION" \
    -f content="$(base64 -i "wg/$f" | tr -d '\n')"
done

# 4. Check the branch before opening anything
gh api "repos/microsoft/winget-pkgs/compare/master...aahepburn:$PKG_ID-$VERSION" \
  -q '"ahead=\(.ahead_by) behind=\(.behind_by)", (.files[] | "  \(.status) \(.filename)")'

# 5. PR
gh pr create --repo microsoft/winget-pkgs --base master \
  --head "aahepburn:$PKG_ID-$VERSION" \
  --title "New version: $PKG_ID version $VERSION"
```

`base64 -i <f> | tr -d '\n'` is the macOS form; on Linux use `base64 -w0 <f>`.

## Gotchas

- **Job IDs change on every re-run attempt.** `gh run rerun --job <id>` fails
  with "cannot be rerun" if you use an ID from an earlier attempt. Re-fetch it.
- **Duplicate installer entries.** An early manual 0.4.6 submission carried a
  stray portable installer entry, and komac inherits the previous version's
  layout, so it can map both a nullsoft and a portable entry onto our single
  `.exe`. winget rejects that as `DuplicateInstallerEntry`. The workflow strips
  any entry carrying `NestedInstallerType` before committing.
- **Locale fields are inherited, then overwritten.** komac copies the previous
  version's locale manifest, which until 0.7.1 still carried the 0.4.5 text
  (`GPL-3.0` instead of `GPL-3.0-or-later`, URLs on the personal account, a
  description of the old chat app). Since 2026-10-22 the "Apply package
  metadata" step rewrites ShortDescription, Description, Tags, License, the
  three URLs and ReleaseNotes from `package.json` (`description`,
  `longDescription`, `keywords`, `license`, `homepage`) and the version's
  `CHANGELOG.md` section. Edit those, not the manifest. The manual submission
  below skips that step, so apply the same fields by hand when submitting manually.
- **The fork is the user's, not the org's.** `fork-user` / `KOMAC_FORK_OWNER`
  must be `aahepburn`. Getting this wrong produces `Could not resolve to a
  Repository with the name 'Quiet-Signals-Lab/winget-pkgs'`.

## History

| Date | Version | Outcome |
|---|---|---|
| 2026-03-22 | 0.4.5 | First manual submission |
| 2026-07-29 | 0.5.1 | winget-releaser action, succeeded |
| 2026-09-09 | 0.5.2 | Action failed 3× on `CreateRef`; submitted by hand ([PR 432197](https://github.com/microsoft/winget-pkgs/pull/432197)); action replaced with komac + `gh` |
| 2026-10-10 | 0.6.0 | komac + `gh` job failed on the fork sync (`workflow` scope); submitted by hand ([PR 450264](https://github.com/microsoft/winget-pkgs/pull/450264)) with license and release notes corrected |
