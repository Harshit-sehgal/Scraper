# pip_audit

- status: failed
- command: `/usr/bin/python3 -m pip_audit`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T12:10:59.624544+00:00
- end_time: 2026-06-12T12:11:16.530639+00:00
- duration_seconds: 16.91
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
Name         Version    ID                  Fix Versions
------------ ---------- ------------------- --------------------
certifi      2023.11.17 PYSEC-2024-230      2024.7.4
certifi      2023.11.17 PYSEC-2024-230      2024.7.4
configobj    5.0.8      CVE-2023-26112      5.0.9
cryptography 41.0.7     PYSEC-2024-225      42.0.4
cryptography 41.0.7     PYSEC-2024-225      42.0.4
cryptography 41.0.7     PYSEC-2026-35       46.0.6
cryptography 41.0.7     PYSEC-2026-35       46.0.6
cryptography 41.0.7     CVE-2023-50782      42.0.0
cryptography 41.0.7     CVE-2024-0727       42.0.2
cryptography 41.0.7     GHSA-h4gh-qq45-vh27 43.0.1
cryptography 41.0.7     CVE-2026-26007      46.0.5
idna         3.6        PYSEC-2024-60       3.7
idna         3.6        PYSEC-2024-60       3.7
idna         3.6        CVE-2026-45409      3.15
jinja2       3.1.2      CVE-2024-22195      3.1.3
jinja2       3.1.2      CVE-2024-34064      3.1.4
jinja2       3.1.2      CVE-2024-56326      3.1.5
jinja2       3.1.2      CVE-2024-56201      3.1.5
jinja2       3.1.2      CVE-2025-27516      3.1.6
lxml         5.2.1      PYSEC-2026-87       6.1.0
lxml         5.2.1      PYSEC-2026-87       6.1.0
pillow       10.2.0     PYSEC-2026-165      12.2.0
pillow       10.2.0     PYSEC-2026-165      12.2.0
pillow       10.2.0     CVE-2024-28219      10.3.0
pillow       10.2.0     CVE-2026-42310      12.2.0
pip          24.0       PYSEC-2026-196      26.1.2
pip          24.0       CVE-2025-8869       25.3
pip          24.0       CVE-2026-1703       26.0
pip          24.0       CVE-2026-3219       26.1
pip          24.0       CVE-2026-6357       26.1
protobuf     4.21.12    CVE-2025-4565       4.25.8,5.29.5,6.31.1
protobuf     4.21.12    CVE-2026-0994       5.29.6,6.33.5
pycares      4.4.0      GHSA-5qpg-rh4j-qp35 4.9.0
pygments     2.17.2     CVE-2026-4539       2.20.0
pyjwt        2.7.0      PYSEC-2026-120      2.12.0
pyjwt        2.7.0      PYSEC-2026-120      2.12.0
pyjwt        2.7.0      PYSEC-2025-183
pyjwt        2.7.0      PYSEC-2026-179      2.13.0
pyjwt        2.7.0      PYSEC-2026-175      2.13.0
pyjwt        2.7.0      PYSEC-2026-177      2.13.0
pynacl       1.5.0      CVE-2025-69277      1.6.2
pyopenssl    23.2.0     CVE-2026-27448      26.0.0
pyopenssl    23.2.0     CVE-2026-27459      26.0.0
requests     2.31.0     CVE-2024-35195      2.32.0
requests     2.31.0     CVE-2024-47081      2.32.4
requests     2.31.0     CVE-2026-25645      2.33.0
sentry-sdk   1.39.2     CVE-2024-40647      1.45.1,2.8.0
setuptools   68.1.2     PYSEC-2025-49       78.1.1
setuptools   68.1.2     PYSEC-2025-49       78.1.1
setuptools   68.1.2     CVE-2024-6345       70.0.0
starlette    1.0.0      PYSEC-2026-161      1.0.1
starlette    1.0.0      PYSEC-2026-161      1.0.1
urllib3      2.0.7      PYSEC-2026-141      2.7.0
urllib3      2.0.7      CVE-2024-37891      1.26.19,2.2.2
urllib3      2.0.7      CVE-2025-50181      2.5.0
urllib3      2.0.7      CVE-2025-66418      2.6.0
urllib3      2.0.7      CVE-2025-66471      2.6.0
urllib3      2.0.7      CVE-2026-21441      2.6.3
wheel        0.42.0     CVE-2026-24049      0.46.2
zipp         1.0.0      CVE-2024-5569       3.19.1
Name                  Skip Reason
--------------------- -------------------------------------------------------------------------------------
bcc                   Dependency not found on PyPI and could not be audited: bcc (0.29.1)
brlapi                Dependency not found on PyPI and could not be audited: brlapi (0.8.5)
command-not-found     Dependency not found on PyPI and could not be audited: command-not-found (0.3)
cupshelpers           Dependency not found on PyPI and could not be audited: cupshelpers (1.0)
dataforge-scraper     Dependency not found on PyPI and could not be audited: dataforge-scraper (0.1.0)
defer                 Dependency not found on PyPI and could not be audited: defer (1.0.6)
kernelstub            Dependency not found on PyPI and could not be audited: kernelstub (3.1.4)
language-selector     Dependency not found on PyPI and could not be audited: language-selector (0.1)
louis                 Dependency not found on PyPI and could not be audited: louis (3.29.0)
pop-transition        Dependency not found on PyPI and could not be audited: pop-transition (1.1.2)
proton-core           Dependency not found on PyPI and could not be audited: proton-core (0.7.4)
proton-keyring-linux  Dependency not found on PyPI and could not be audited: proton-keyring-linux (0.2.1)
proton-vpn-api-core   Dependency not found on PyPI and could not be audited: proton-vpn-api-core (5.2.4)
proton-vpn-cli        Dependency not found on PyPI and could not be audited: proton-vpn-cli (1.0.1)
proton-vpn-daemon     Dependency not found on PyPI and could not be audited: proton-vpn-daemon (0.13.7)
proton-vpn-gtk-app    Dependency not found on PyPI and could not be audited: proton-vpn-gtk-app (4.16.5)
python-apt            Dependency not found on PyPI and could not be audited: python-apt (2.7.7+ubuntu5.2)
python-debian         Dependency not found on PyPI and could not be audited: python-debian (0.1.49+ubuntu2)
repolib               Dependency not found on PyPI and could not be audited: repolib (2.2.2)
repoman               Dependency not found on PyPI and could not be audited: repoman (1.4.0)
sessioninstaller      Dependency not found on PyPI and could not be audited: sessioninstaller (0.0.0)
ubuntu-drivers-common Dependency not found on PyPI and could not be audited: ubuntu-drivers-common (0.0.0)
ufw                   Dependency not found on PyPI and could not be audited: ufw (0.36.2)
variety               Dependency not found on PyPI and could not be audited: variety (0.9.0)
xkit                  Dependency not found on PyPI and could not be audited: xkit (0.0.0)

```

## stderr

```text
Found 60 known vulnerabilities in 21 packages

```
