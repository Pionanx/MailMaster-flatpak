#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DOWNLOAD_URL = "https://u.163.com/linuxds"
DOWNLOAD_REFERER = "https://dashi.163.com/index.html"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) MailMaster-flatpak-check"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def request(url: str, github: bool = False) -> urllib.request.Request:
    if github:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "mailmaster-flatpak-release-check",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    else:
        headers = {
            "Accept": "application/octet-stream,*/*;q=0.8",
            "Referer": DOWNLOAD_REFERER,
            "User-Agent": USER_AGENT,
        }
    return urllib.request.Request(url, headers=headers)


def download_deb(output: Path) -> tuple[str, str]:
    import hashlib

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    effective_url = DOWNLOAD_URL
    if shutil.which("curl"):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--location",
                    "--retry",
                    "3",
                    "--connect-timeout",
                    "30",
                    "--max-time",
                    "600",
                    "-A",
                    USER_AGENT,
                    "-e",
                    DOWNLOAD_REFERER,
                    "-o",
                    str(tmp),
                    "-w",
                    "%{url_effective}",
                    DOWNLOAD_URL,
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            effective_url = result.stdout.strip() or DOWNLOAD_URL
        except subprocess.CalledProcessError as exc:
            fail(f"failed to download {DOWNLOAD_URL} with curl: exit {exc.returncode}")
    else:
        try:
            with urllib.request.urlopen(request(DOWNLOAD_URL), timeout=600) as response, tmp.open("wb") as fh:
                effective_url = response.geturl()
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
        except urllib.error.HTTPError as exc:
            fail(f"failed to download {DOWNLOAD_URL}: HTTP {exc.code}")
        except Exception as exc:
            fail(f"failed to download {DOWNLOAD_URL}: {exc}")
    digest = hashlib.sha256()
    with tmp.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    tmp.replace(output)
    return digest.hexdigest(), effective_url


def deb_field(path: Path, field: str) -> str:
    try:
        return subprocess.check_output(
            ["dpkg-deb", "-f", str(path), field],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception as exc:
        fail(f"failed to read {field} from {path}: {exc}")


def fetch_json(url: str, allow_404: bool = False) -> dict | None:
    try:
        with urllib.request.urlopen(request(url, github=True), timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        fail(f"failed to fetch {url}: HTTP {exc.code}")
    except Exception as exc:
        fail(f"failed to fetch {url}: {exc}")


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def github_tag_url(repo: str, tag: str) -> str:
    quoted_tag = urllib.parse.quote(tag, safe="")
    return f"https://api.github.com/repos/{repo}/releases/tags/{quoted_tag}"


def write_outputs(outputs: dict[str, str]) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value.replace(chr(10), ' ')}\n")

    generated = Path("build/generated")
    generated.mkdir(parents=True, exist_ok=True)
    with (generated / "check.env").open("w", encoding="utf-8") as fh:
        for key, value in outputs.items():
            escaped = value.replace(chr(39), chr(39) + chr(34) + chr(39) + chr(34) + chr(39))
            fh.write(f"{key.upper()}='{escaped}'\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve whether a NetEase Mail Master Flatpak release should be built.")
    parser.add_argument(
        "--packaging-repo",
        required=True,
        help="This GitHub repository in owner/name form, for example user/MailMaster-flatpak.",
    )
    parser.add_argument(
        "--force",
        default="false",
        help="Build even when the matching packaging release already exists.",
    )
    args = parser.parse_args()

    deb_path = Path("build/downloads/mail.deb")
    asset_sha256, asset_url = download_deb(deb_path)
    version = deb_field(deb_path, "Version")
    package_name = deb_field(deb_path, "Package")

    release_tag = f"mailmaster-{version}"
    existing_release = fetch_json(github_tag_url(args.packaging_repo, release_tag), allow_404=True)
    exists = existing_release is not None
    force = parse_bool(args.force)
    should_build = force or not exists

    if should_build:
        reason = "forced rebuild" if force and exists else "new upstream package"
    else:
        reason = f"{release_tag} already exists"

    outputs = {
        "tag": version,
        "version": version,
        "release_tag": release_tag,
        "asset_name": "mail.deb",
        "asset_url": asset_url,
        "asset_sha256": asset_sha256,
        "package": package_name,
        "should_build": "true" if should_build else "false",
        "exists": "true" if exists else "false",
        "reason": reason,
    }
    write_outputs(outputs)

    print(f"Official package: {package_name}")
    print(f"Version: {version}")
    print(f"Packaging release tag: {release_tag}")
    print(f"Asset URL: {asset_url}")
    print(f"Asset SHA256: {asset_sha256}")
    print(f"Existing packaging release: {outputs['exists']}")
    print(f"Should build: {outputs['should_build']} ({reason})")


if __name__ == "__main__":
    main()
