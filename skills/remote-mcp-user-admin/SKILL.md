---
name: remote-mcp-user-admin
description: Drive the sendable Remote MCP user administration package for admin-only user creation, profile updates, role changes, activation status changes, and repo-access management through numbered selection menus.
---

# Remote MCP User Admin

Use this skill when the user asks to manage Remote MCP users, allowed users,
system roles, user activation status, or repo access through the sendable
`remote-mcp-user-admin` package.

## Operating Contract

- Use the packaged command-line tool as the source of truth for menu options and
  write confirmations.
- Keep reasoning in Codex. Let the script do mechanical remote MCP calls, state
  files, confirmation files, and diagnostics.
- Start with:

  ```bash
  python3 dist/remote-mcp-user-admin/remote_mcp_user_admin_tui.py --agent-action user-list
  ```

- If `WORKFLOW_ORCH_USER_ADMIN_COMMAND_PREFIX` is configured, use the returned
  `nextCommandTemplate` exactly rather than reconstructing the command.
- Present `options` and `navigationOptions` as numbered choices to the user.
- When the user selects an option, run the returned `nextCommandTemplate` with
  the placeholder replaced by the selected value.
- Treat `selectionRequired: true` as a stop for administrator input unless the
  user already gave a clear selection in the current turn.
- Treat `finalOk: true` with no selection required as completion for that step.

## Safety Rules

- This functionality is admin-only. If the package returns
  `errorCode: "ADMIN_REQUIRED"`, report that admin credentials are required and
  stop.
- Do not call `workflow.user.delete` or `workflow.user.rotate_token`; they are
  out of scope for this package.
- Do not print, summarize, or expose token values. For `create-user-apply`, pass
  `--token-output-file <secure-local-path>` only when the administrator asks to
  receive the generated token.
- Never paste token keys, JWTs, challenge codes, or secrets into the chat.
- Keep generated confirmation JSON files in place until the package applies or
  discards them.

## Challenge Auth

If the package returns `decisionType: "auth_challenge_required"`:

1. Tell the user to put the emailed challenge code in a local text file.
2. Run the returned `nextCommandTemplate` after the user provides the file path.
3. Do not put the challenge code itself in chat.

## Common Flow

1. Run `--agent-action user-list`.
2. Show users sorted by last name, plus the final `Add New User` option.
3. For an existing user, run the selected user-detail command and show the
   detail-action menu.
4. For repo access, allow repeated add/remove choices in the same draft before
   running save/review.
5. For every write, use the package-generated confirmation command.
6. If `decisionType: "stale_user_data"` is returned, show Refresh, Overwrite,
   Cancel, and Exit exactly as returned by the package.
