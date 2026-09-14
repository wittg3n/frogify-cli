# Security Policy

Thank you for helping keep Frogify and its users secure.

## Supported Versions

Security fixes are provided for the latest stable release of Frogify. Older releases may not receive security updates.

| Version               | Supported       |
| --------------------- | --------------- |
| Latest stable release | ✅               |
| Older releases        | ❌ / best effort |

Users should reproduce a suspected vulnerability against the latest available version before reporting it whenever possible.

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

Please use GitHub's private vulnerability reporting for this repository:

https://github.com/wittg3n/frogify-cli/security/advisories/new

When submitting a report, include as much of the following as possible:

* the affected Frogify version or commit;
* your operating system and Python version;
* a clear description of the vulnerability and its potential impact;
* minimal steps required to reproduce the issue;
* a proof of concept, logs, or stack trace when useful;
* whether the issue requires unusual configuration or user interaction;
* any suggested mitigation or fix, if you have one.

Please remove API keys, access tokens, cookies, personal data, and unrelated copyrighted content from reports and reproduction material.

## What Counts as a Security Issue

Examples include, but are not limited to:

* command, argument, or shell injection;
* unsafe path handling, path traversal, or unintended file overwrite;
* arbitrary code execution;
* credential, token, cookie, or sensitive-data exposure;
* vulnerabilities in dependency usage that are exploitable through Frogify;
* malicious input that bypasses expected validation or trust boundaries.

Ordinary download failures, rate limits, incorrect track matching, provider availability, feature requests, and general bugs should be reported through the normal GitHub issue tracker unless they create a security impact.

## Disclosure Process

Frogify follows coordinated disclosure. Please give the maintainer a reasonable opportunity to investigate and release a fix before publishing technical details or proof-of-concept code.

The project aims to:

* acknowledge a valid security report within 5 business days;
* provide an initial assessment within 10 business days when practical;
* keep the reporter informed about meaningful progress;
* credit reporters in a security advisory or release notes when requested and appropriate.

Response times may vary because Frogify is maintained as an open-source project.

## Safe Harbor

Good-faith security research intended to identify and responsibly report vulnerabilities is welcome. Please avoid privacy violations, destructive testing, service disruption, accessing data that is not yours, or testing against third-party services in ways that violate their rules.

Thank you for reporting vulnerabilities responsibly.
