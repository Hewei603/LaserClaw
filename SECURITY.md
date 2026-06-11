# Security Policy

LaserClaw handles experiment metadata, uploaded documents, generated artifacts, and retrieval traces. Treat deployments as sensitive unless all data is synthetic.

## Supported Versions

Security fixes are applied to the current main development line until formal releases are established.

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability. Contact the maintainers privately with:

- affected endpoint or component,
- reproduction steps,
- expected and observed access boundaries,
- relevant configuration values with secrets removed.

## Security Expectations

- Enable `REQUIRE_AUTH=true` and configure `API_KEY` outside local demos.
- Use project-level ACL for private or collaborative case data.
- Keep real lab documents and private eval datasets out of Git.
- Rotate provider API keys if they may have been exposed.
- Review uploaded documents before marking knowledge sources as approved.

## Known Limitations

LaserClaw is an advisory knowledge workspace. It does not operate laser hardware and must not be used as an automated safety controller. AI-generated outputs require qualified human review and applicable SOP approval.
