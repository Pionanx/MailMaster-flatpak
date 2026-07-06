#!/usr/bin/env python3
import argparse
import datetime as dt
import email.utils
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


DOWNLOAD_URL = "https://u.163.com/linuxds"
DOWNLOAD_REFERER = "https://dashi.163.com/index.html"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) MailMaster-flatpak"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream,*/*;q=0.8",
            "Referer": DOWNLOAD_REFERER,
            "User-Agent": USER_AGENT,
        },
    )


def download_deb(output: Path) -> tuple[str, str, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    effective_url = DOWNLOAD_URL
    last_modified = ""
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
                last_modified = response.headers.get("Last-Modified", "")
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
    return digest.hexdigest(), effective_url, last_modified


def deb_field(path: Path, field: str) -> str:
    try:
        return subprocess.check_output(
            ["dpkg-deb", "-f", str(path), field],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception as exc:
        fail(f"failed to read {field} from {path}: {exc}")


def release_date(last_modified: str) -> str:
    if last_modified:
        try:
            return email.utils.parsedate_to_datetime(last_modified).date().isoformat()
        except Exception:
            pass
    return dt.date.today().isoformat()


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the official NetEase Mail Master Linux deb and generate Flatpak inputs."
    )
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Packaging repository root.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    deb_path = repo_root / "build" / "downloads" / "mail.deb"
    asset_sha256, asset_url, last_modified = download_deb(deb_path)
    version = deb_field(deb_path, "Version")
    package_name = deb_field(deb_path, "Package")
    date = release_date(last_modified)
    bundle_name = f"MailMaster-{version}-x86_64.flatpak"

    manifest_template = (repo_root / "com.netease.MailMaster.yml.in").read_text(encoding="utf-8")
    manifest = manifest_template.replace("@MAILMASTER_DEB_PATH@", "build/downloads/mail.deb")
    write_text(repo_root / "com.netease.MailMaster.yml", manifest)

    metainfo_template = (
        repo_root / "flatpak" / "com.netease.MailMaster.metainfo.xml.in"
    ).read_text(encoding="utf-8")
    metainfo = metainfo_template.replace("@VERSION@", version).replace("@RELEASE_DATE@", date)
    write_text(repo_root / "build" / "generated" / "com.netease.MailMaster.metainfo.xml", metainfo)

    env = {
        "MAILMASTER_PACKAGE": package_name,
        "MAILMASTER_VERSION": version,
        "MAILMASTER_RELEASE_DATE": date,
        "MAILMASTER_ASSET_NAME": "mail.deb",
        "MAILMASTER_ASSET_URL": asset_url,
        "MAILMASTER_ASSET_SHA256": asset_sha256,
        "BUNDLE_NAME": bundle_name,
    }
    env_text = "".join(f"{key}={sh_quote(value)}\n" for key, value in env.items())
    write_text(repo_root / "build" / "generated" / "release.env", env_text)

    print(f"Generated Flatpak inputs for NetEase Mail Master {version}")
    print(f"Asset URL: {asset_url}")
    print(f"SHA256: {asset_sha256}")


if __name__ == "__main__":
    main()
