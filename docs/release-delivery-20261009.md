# Windows alpha.2 and production delivery

Explicit owner release/deployment request: 9 October 2026. Public Windows **0.4.0-alpha.2** and the completed **42-second release trailer** are delivered.

| Deliverable | Result |
| --- | --- |
| Windows installer / portable ZIP | Published: https://github.com/alibad/RTSAI-Mod/releases/tag/v0.4.0-alpha.2 |
| Website / verified download | https://rtsai.net/download; native Vercel Git integration deployed website main |
| Browser game | https://rtsai.net/play/; live peer regression passed after the website deployment |
| Release trailer | https://rtsai.net/trailer/rtsai-trailer.mp4; homepage playback and full-video link live |
| Windows signing | Unsigned: no certificate or signing configuration selected. No purchase or self-signed trust substitution |
| Installed game | `%LOCALAPPDATA%/Programs/RTS AI/RTSAI.exe`, alpha.2, No AI selected; Start menu entry present |

Windows game content was built from canonical product `d1b3c36d144763175ad641a3c7379ea8dd9d3646`, using shared engine `aed51fe4b1c699b487b9f9683dbc79215f3a96be`. Release notes and version-aware installer acceptance helper were then committed at product main/tag `fe27626ce36e63aebafb410ee27204c1d0f24af5`. Website main `ceb4ecaa9c4c2b2571cdab50fdfaaff0f0e1a134` deployed to Vercel production `dpl_EUMshPi6zRmReKvWiTF5AfjMF6Rk`; its GitHub Vercel commit status is success, and rtsai.net/www.rtsai.net alias this deployment.

The exact installer passed installation, recorded configuration, shortcut target, rendered mode switching, bot skirmishes in both modes, uninstallation and unrelated-file preservation on the owner's PC. It was subsequently reinstalled and launched successfully. The extracted portable ZIP matched every one of the **6,398** staged payload hashes and passed mode switching. A fresh-support-directory run on this developer PC is not fresh-OS acceptance.

Live website acceptance downloaded the installer through the real download button and verified its full hash. It checked trailer duration, mute default, play/pause, reduced motion, complete media digest and absence of page errors. The website production build, content checks and type checks passed; **261 tests passed, four skipped**, and lint passed. Current rule facts and dependency exports were regenerated without changing actor contracts, owner gates or artwork. Trailer full decode, stream/duration checks, frame review and historical film source gates passed. All historical films, custom sources and provenance remain preserved. The trailer uses original music, with no Windows system narration.

After production deployment, Chrome–Edge peer gameplay, both player deployment orders, bidirectional chat, synthetic audio/video and disconnect handling passed with **399 matching simulation frames**, zero room API requests and no page errors. Earlier Chrome–Firefox acceptance also passed. All these peers used this PC/network. Different devices/networks, real camera/microphone quality and Safari remain pending; some direct connections can fail without TURN relay fallback.

| Artifact | SHA-256 |
| --- | --- |
| Installer | `92beddabfc7d0de2ebced69dff4c818fea62f6db61e1156eaec666984cf30326` |
| Portable ZIP | `00a43c4bb72e79d8569a0fd6c5a6ac5b418923f8b2aae161c74dfb9aa884f7f3` |
| Trailer | `dec4ccae13f05159b2015bdcd9f5ee714084227b89f434a2ddf44bc5faff8385` |

Raw artifact/evidence root: `D:/rtsai-release/alpha2-20261009`. Installer acceptance: `D:/rtsai-release/online-e2e-alpha2-20261009`. Build/test/deployment logs: `games/artifacts/consolidation-20261009`. Reproducible trailer source: `RTSAI-Film/tools/build_release_trailer.py`; website acceptance: `RTSAI-Web/scripts/release-browser-acceptance.mjs`.

macOS, full historical Classic parity, human campaign playability, competitive balance, fluent non-English voice approval and remaining workshop/native parity are still roadmap work. This public alpha does not imply their completion. No new worktree, hosted CI, paid service or certificate purchase was added.
