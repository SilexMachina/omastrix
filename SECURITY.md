# Security

## Status and boundaries

This is experimental preview software. No supported stable release or security
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
safety. Catalog model URLs use immutable revisions and expected file metadata. A
checksum first computed from an arbitrary added link is not publisher
verification. Treat added URLs, model files, and recipe flags as untrusted input.

`~/.config/omastrix/webui.env` contains a secret. Do not commit or share it, copy
secrets from unrelated installs, or include WebUI databases, prompts, chat logs,
auth tokens, or credential-bearing URLs in reports. GTT writes require explicit
consent and privilege escalation; the panel itself must not run as root.

## Engine API access

The current preview runs the engine router and model-worker HTTP listeners on
loopback without API authentication. The fork's permissive cross-origin policy
can allow web pages with browser access to loopback to make engine requests.
Local processes can also use those interfaces. WebUI login protects its own
web interface; direct engine requests have separate, unauthenticated access.

Keep engine ports private, avoid forwarding or tunnelling them, and use a
trusted browser environment. Do not assume that configuring a router API key
alone protects every model-worker listener. Complete engine authentication is
outside the current preview's protection boundary.

## GTT authorization boundary

GTT changes currently run code from the user-owned plugin checkout with
administrator privileges after a Polkit prompt. Modifying that checkout can
change the code executed with that approval, including imported modules.
Protect the checkout, review updates, and approve GTT changes only when you
trust its contents. The current preview does not isolate these writes behind
a root-owned helper. Normal panel, engine and WebUI processes run as your user.

## Reporting

Do not post exploit details or secrets in public issues. Use
[private vulnerability reporting](https://github.com/SilexMachina/omastrix/security/advisories/new),
which is enabled for this repository. No response-time commitment is currently
advertised.

Include affected commit/version, impact, minimal reproduction, and redacted
logs. Do not test against other people's hosts or perform destructive/live-service
experiments without their permission. If credentials were exposed, notify their
owner privately and rotate them through the appropriate provider rather than
pasting them into a report.
