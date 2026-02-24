# Project Tasks & Assignments

## Current Sprint

### High Priority

Yang Li needs to work on the authentication module. We need OAuth2 support for both GitHub and Google login. Should include session management too. This is blocking other features.

The sync engine needs better error handling - when API fails, it should retry with backoff. Also need to log failures properly. Maybe Yang can look at this after auth?

### Medium Priority

- Add unit tests for the sync engine (test status mapping, outbox processing)
- Documentation needs updating - the README is outdated
- Consider adding webhook support instead of polling

### Low Priority

Someone should improve the error messages - they're not user-friendly right now.

## Team Notes

Yang Li (yli9919@hku.hk) is the main developer. He's handling backend and sync logic.

We might need to bring in someone for frontend later.

## Backlog Ideas

- Multi-repo support
- Real-time notifications via Lark bot
- Dashboard for sync status
- API rate limiting handling

## Questions to Resolve

- Should we use webhooks or keep polling?
- What's the retention policy for sync logs?
- Do we need audit trail for compliance?
