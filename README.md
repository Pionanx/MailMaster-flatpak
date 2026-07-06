# NetEase Mail Master Flatpak Release Packaging

This repository packages the upstream NetEase Mail Master Linux `.deb` from
the official download site as a Flatpak app. The GitHub workflow publishes both
a single-file `.flatpak` bundle to GitHub Releases and an updateable Flatpak
repository to GitHub Pages.

Upstream download page: <https://dashi.163.com/index.html>

## Local Build

Install Flatpak tooling and the GNOME runtime:

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder org.gnome.Platform//49 org.gnome.Sdk//49
```

Build from the current official Linux download:

```bash
./scripts/build-flatpak.sh
```

The output is written to `dist/`:

```bash
flatpak install --user -y dist/MailMaster-5.0.2.1011-x86_64.flatpak
flatpak run com.netease.MailMaster
```

The script also prepares a static Flatpak repository under `dist/pages/`. For
local testing without GPG signing:

```bash
flatpak --user remote-add --if-not-exists --no-gpg-verify mailmaster dist/pages/repo
flatpak --user install -y mailmaster com.netease.MailMaster
flatpak --user update com.netease.MailMaster
```

## Updateable Flatpak Repository

After a successful workflow run, GitHub Pages serves:

- `https://pionanx.github.io/MailMaster-flatpak/mailmaster.flatpakrepo`
- `https://pionanx.github.io/MailMaster-flatpak/com.netease.MailMaster.flatpakref`
- `https://pionanx.github.io/MailMaster-flatpak/repo/`

Enable GitHub Pages for this repository with source set to **GitHub Actions**.
Then users can add the remote and receive updates from future workflow runs:

```bash
flatpak remote-add --user --if-not-exists mailmaster \
  https://pionanx.github.io/MailMaster-flatpak/mailmaster.flatpakrepo
flatpak install --user mailmaster com.netease.MailMaster
flatpak update --user com.netease.MailMaster
```

## GPG Signing

This repository expects the shared Flatpak repository signing key to be
configured as GitHub Secrets:

- `FLATPAK_GPG_PRIVATE_KEY`
- `FLATPAK_GPG_PUBLIC_KEY`

And this GitHub Actions variable:

- `FLATPAK_GPG_KEY_ID`

The workflow fails if signing secrets are missing, so it does not accidentally
publish an unsigned repository.

## GitHub Release

Run the `Build Flatpak Release` workflow manually with `force=true` to rebuild
the current official Linux package.

The workflow also runs every 6 hours. Scheduled runs download the current
official Linux `.deb`, read its Debian package version, and only build when this
packaging repository does not already have the matching release tag.

The workflow:

1. Downloads the official Linux `.deb` with the required official-site Referer.
2. Reads the package version from the Debian control metadata.
3. Checks whether `mailmaster-<version>` already exists in this repository.
4. Generates the Flatpak manifest from the downloaded local `.deb`.
5. Builds `MailMaster-<version>-x86_64.flatpak` and an OSTree Flatpak repository.
6. Deploys the Flatpak repository to GitHub Pages.
7. Publishes the bundle to this repository under release tag
   `mailmaster-<version>`.

## Flatpak Permissions

The manifest includes the permissions a desktop email client needs:

- Network access for mail accounts and web login/OAuth flows.
- X11 display access and IPC for the bundled Qt5/CEF UI.
- PulseAudio and DRI access for notification sounds and accelerated rendering.
- Document, download, desktop, picture, and video folders for attachments.
- Notification, portal, secret-service, and tray D-Bus integration.

Broad host filesystem access and unrestricted device access are intentionally
not enabled.

