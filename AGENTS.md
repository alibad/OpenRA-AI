# OpenRA AI game guidance

- Follow the shared workspace rules in `../AGENTS.md`.
- Implement and validate game UX directly in the OpenRA codebase; Figma is not part of this product workflow.
- Keep AI interactions native to the game, interruptible, non-blocking, and subordinate to gameplay.
- Keep Earth-to-Battlefield output playable by relying on OpenRA terrain, pathing, resource, spawn, and map-validation systems.
- Prefer local test scripts and local game runs. Never add GitHub Actions or hosted workflow files.

## Worktrees require an explicit owner request (15 October 2026)

- Use the existing canonical checkout. Do not create a Git worktree or a parallel clone unless the owner explicitly asks for it in the current task. This supersedes older instructions permitting worktrees for concurrency, isolation, convenience, or risk.
- Another session using the checkout is not permission to create a worktree. Coordinate non-overlapping changes, wait, or report the specific blocker; preserve all in-progress work.
- In the OpenRA/RTS AI repositories, work and commit on canonical `main`. Fetch the correct owner remote and safely incorporate its main before starting, committing, or validating a build. Never reset, force-push, or rewrite another session's commits.
- If the owner explicitly authorizes a worktree, keep it temporary, start from current main, and integrate validated work back into canonical main. Do not leave the only copy of finished work on a branch or worktree.
- Before retiring an existing branch or worktree, verify that its unique commits, uncommitted files, and user artifacts are preserved and integrated where appropriate. Never delete unique work to make a checkout look clean.
- Keep this policy change and local consolidation local. A request to consolidate on main does not by itself authorize a push, deployment, release, or deletion of branches/worktrees.
