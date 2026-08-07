# Launcher

The installed launcher is the local product shell for Windows and macOS.

Responsibilities:

- install and update the compatible OpenRA AI game build;
- manage required game assets without redistributing unlicensed content;
- register and handle `openra-ai://` links from the web application;
- download, verify, install, and remove mission packages;
- launch the game with the selected mission;
- start and stop the local companion bridge;
- display download progress and actionable errors;
- support full offline play for already-installed content.

The UI framework will be selected after a small Windows/macOS spike comparing
native packaging, update support, code sharing with the web app, signing, and
accessibility.

