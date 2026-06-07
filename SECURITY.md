# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's **private vulnerability
reporting**: open the repository's **Security** tab → **Report a vulnerability**
(this opens a private GitHub Security Advisory). Do **not** file a public issue
for a suspected vulnerability.

We aim to acknowledge a report within a few days and to coordinate a fix and
disclosure timeline with you.

## Supported versions

tablecodec is pre-1.0 (`0.0.x`). Only the **latest released version** receives
fixes; there is no back-porting to older `0.0.x` patches. A long-term-support
line begins at `1.0.0`.

| Version | Supported |
|---------|-----------|
| latest `0.0.x` | yes |
| older `0.0.x`  | no  |

## Supply-chain assurances

How a tablecodec release is built and published (see
[ADR 0014](docs/adr/0014-release-via-oidc-trusted-publishing.md)):

- **Zero-dependency runtime core.** The published package declares no
  third-party runtime dependencies; this is enforced in CI by a Semgrep rule.
  Optional features (`[cli]`, `[teds]`, `[hf]`) are the only place third-party
  code is pulled in, and never by `import tablecodec`.
- **Tokenless publishing (OIDC Trusted Publishing).** Releases are published
  from GitHub Actions via PyPI Trusted Publishing. No long-lived PyPI API token
  exists in the repo, in CI secrets, or in any maintainer keychain.
- **PEP 740 publish attestations.** Each PyPI artifact carries a PEP 740
  attestation, generated automatically during Trusted Publishing.
- **SLSA build provenance.** A separate GitHub artifact attestation
  (build provenance) is recorded for every distribution and can be verified
  with `gh attestation verify <file> --repo hironow/tablecodec`.
- **SHA-pinned GitHub Actions.** Every action is pinned to a full commit SHA,
  with Dependabot tracking updates behind a 7-day cooldown.
- **Screened install registry.** CI installs route through a screening proxy
  (Takumi Guard) that blocks known-malicious packages before they execute.

## Verifying a downloaded release

```sh
pip install tablecodec
python -c "import tablecodec; print(tablecodec.__version__)"

# Verify the GitHub SLSA build provenance for a downloaded wheel/sdist:
gh attestation verify <tablecodec-*.whl> --repo hironow/tablecodec
```

The PyPI project page also shows the Trusted Publishing source and the PEP 740
attestation for each release file.
