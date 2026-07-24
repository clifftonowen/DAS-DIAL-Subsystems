# Team collaboration (8 devs, full-stack)

Two layers keep us from overlapping and stop most frontend merge conflicts:
**GitHub Issues** = who's doing what (tasks). **GitLive** = who's editing which file *right now*.

## Workflow — the anti-overlap habit

1. **Claim it.** Open/pick an Issue and **assign yourself** before writing code. No issue = invisible work.
2. **Draft PR early.** Push your branch and open a **draft PR** immediately (link the issue). This is
   the signal to everyone that you're on this area.
3. **Small & short.** Keep PRs small; merge within a day or two. A week-old branch *will* conflict.
4. **Rebase daily.** `git pull --rebase origin main` every day so you conflict early and small.
5. **Lockfile conflicts:** don't hand-merge `package-lock.json` — take main's version, re-run
   `npm install`, commit.

Branch naming: `feat/<short-desc>` or `fix/<short-desc>`.

## GitLive — real-time "who's in this file" (all 8 must install)

GitLive shows teammates' branches and the files they're editing live, and **warns you as you type**
if someone else is in the same file on another branch — catching conflicts before they happen.

**Setup (each person, ~2 min):**
1. Install **GitLive** — VS Code: Marketplace → search "GitLive"; JetBrains: Settings → Plugins → "GitLive".
2. Reload the editor, **sign in with GitHub**, and authorize this repo.
3. That's it — teammate avatars now appear on branches/files in the sidebar.

**Notes:**
- Everyone must install it **and** be on VS Code or JetBrains — anyone else is invisible to the tool.
- It **complements** the draft-PR habit, it doesn't replace it. If GitLive flags a shared file, ping
  that person before diving in.

## Labels (create once)

Labels aren't a repo file — add them under **Issues → Labels** (or `gh label create "<name>"`):

`type:feature` · `type:bug` · `type:chore` · `area:frontend` · `area:backend` ·
`status:wip` · `status:blocked` · `needs-review`
