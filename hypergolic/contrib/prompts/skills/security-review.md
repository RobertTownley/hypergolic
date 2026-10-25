Examine the change through an attacker's lens. Every finding cites file:line and the attack it enables

## Injection

- SQL: raw string interpolation in queries; ORM escape hatches (`text()`, `raw`)
- Command: user input reaching `subprocess`, `exec`, `os.system`, shell strings
- XSS: unescaped user input in DOM (`dangerouslySetInnerHTML`, `v-html`, template literals)
- Path traversal: user-controlled paths without normalization/containment checks
- Deserialization: untrusted data to `pickle`, `yaml.load`, `eval`
- SSRF: user-controlled URLs fetched server-side

## AuthN & AuthZ

- New endpoints/routes missing auth middleware
- Authorization enforced at the service/data layer, not just the handler
- IDOR: can one user reach another's resources by changing an ID?
- Token handling: expiry honored, no secrets in localStorage or logs
- Default-deny — flag any new allow-by-default path

## Data Exposure & Input Validation

- Secrets or PII in code, config, logs, or error responses
- API responses including fields the client shouldn't see
- External input validated server-side at the boundary, with size/length limits

Dependencies: new deps — known CVEs, pinned versions, appropriate scope (dev vs prod)

Cite the OWASP category when relevant. Confirm exploitability when you can (craft the malicious input); say so when you can't
