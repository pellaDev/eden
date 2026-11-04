# Third-party software

Eden's own code is MIT-licensed (see `LICENSE`). It uses the packages below, each under its own license. They are
installed from their own registries (`requirements.txt`, `windows/requirements-windows.txt`, `webui/package.json`);
Eden does not copy their code into this repository.

| Package | Used for | License |
|---|---|---|
| FastAPI | admin API | MIT |
| Starlette | web framework under FastAPI | BSD-3-Clause |
| Uvicorn | web server | BSD-3-Clause |
| Pydantic | request validation | MIT |
| PyOTP | one-time codes for the remote login | MIT |
| qrcode | QR code of the one-time-code enrollment | BSD |
| Pillow | image output of qrcode | MIT-CMU (HPND) |
| psutil (Windows edition) | network adapter, connections | BSD-3-Clause |
| React, React DOM | web UI | MIT |
| React Router | web UI routing | MIT |
| Vite | web UI build | MIT |
| TypeScript | web UI type checking | Apache-2.0 |
| Recharts | traffic chart | MIT |
| Lucide | icons | ISC |
| PDS (`@workspace/pds`) | web UI components | MIT |

The web UI's lockfile (`webui/pnpm-lock.yaml`) pins every transitive dependency; they are MIT, ISC, BSD, Apache-2.0
or 0BSD licensed, except `caniuse-lite` (CC-BY-4.0), which is a build-time data package and is not shipped in the
built UI. Run `pnpm licenses list` in `webui/` for the complete, current list.

PDS is installed from its own GitHub repository (`github:pellaDev/PDS`), pinned by commit in the lockfile.
