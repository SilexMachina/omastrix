# Security

## Status and boundaries

This is unreleased development software. No supported stable release or security
update SLA is established yet. Test on a host you are authorized to modify and
keep a recovery path for boot/GTT changes.

The inference engine stays on `127.0.0.1:8080`. New Open WebUI installs default
to loopback on port 3000. Create the first administrator locally, then stop the
service and explicitly confirm Local network access if needed. Network starts
require an existing administrator in the product SQLite database; the generated
wrapper enforces the check even for a direct service start. Authentication stays
on and general signup stays off. Existing host choices are preserved.

Local network binds all IPv4 interfaces. OmaStrix provides no TLS or firewall
policy; keep port 3000 off the public internet and restrict clients. Custom
database network configuration is unsupported and refused by the guard.

Engine builds, Python packages, and model downloads are supply-chain inputs.
An expected SHA-256 verifies bytes against a trusted expectation, not a model's
safety. Catalog model URLs now use immutable revisions and expected file metadata;
end-to-end existing-file verification remains a release acceptance item. A
checksum first computed from an arbitrary added link is not publisher
verification. Treat added URLs, model files, and recipe flags as untrusted input.

`~/.config/omastrix/webui.env` contains a secret. Do not commit or share it, copy
secrets from unrelated installs, or include WebUI databases, prompts, chat logs,
auth tokens, or credential-bearing URLs in reports. GTT writes require explicit
consent and privilege escalation; the panel itself must not run as root.

## Reporting

Do not post exploit details or secrets in public issues. Use GitHub's private
vulnerability reporting for this repository **if enabled**; otherwise contact
the maintainer privately through the channel used to obtain repository access
and request a secure reporting route. No public reporting address or enabled
GitHub reporting feature is asserted here. Establish a usable private reporting
route before opening the repository to the public.

Include affected commit/version, impact, minimal reproduction, and redacted
logs. Do not test against other people's hosts or perform destructive/live-service
experiments without their permission. If credentials were exposed, notify their
owner privately and rotate them through the appropriate provider rather than
pasting them into a report.
