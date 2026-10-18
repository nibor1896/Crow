[← README](../../README.md) · [Docs index](../README.md)

# Repo

| path | |
|---|---|
| `cli/crow_gui.py` | the window — the client |
| `cli/crow_core.py` | conversation, request, SSE, tool loop, memory, skills, goals, delegation, MCP, cost line |
| `cli/crow_platform.py` | the platform seam: paths, process discovery, spawn and kill, per OS |
| `cli/crow_voice.py` | dictation |
| `install.ps1` · `install.sh` | the two installers, one contract |
| `tools/start-server.py` | model picker, becomes the inference server |
| `tools/build-llama-server.sh` | builds the CUDA engine on Linux, where there is no release asset |
| `tools/build-sd-server.sh` | builds `sd-server` and `sd-cli` (stable-diffusion.cpp 2f88688, CUDA) for the image tools on Linux; `install.sh --build-image-server` runs it (#314) |
| `kits/pathtracer/` | the voxel kit (#298): vendored three + three-mesh-bvh + three-gpu-pathtracer (`crow-pathtracer.js`, `kit.json`, `LICENSE.*`), `voxel-kit.js`, `scaffold/`, `SKILL.md`, `check_diorama.py` (#299) |
| `tools/build-pathtracer-kit.sh` | rebuilds the bundle from the exact npm pins (`just pathtracer-kit`) |
| `tools/check_pathtracer_kit.py` | holds bundle, licence texts and NOTICE against `kits/pathtracer/kit.json` |
| `manifests/operating-point.json` | source of truth for every server command line |
| `manifests/shared-core.json` | what may exist only once, and where |
| `tools/check_operating_point.py` | holds every written copy against that manifest |
| `docs/operating-points.md` | the four measured lines, and the servers `install.ps1` sets up |

---
