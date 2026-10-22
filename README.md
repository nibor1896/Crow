<picture>
  <source media="(max-width: 700px) and (prefers-color-scheme: dark)" srcset="docs/images/readme/crow-mobile-dark.svg?v=20261022c">
  <source media="(max-width: 700px)" srcset="docs/images/readme/crow-mobile-light.svg?v=20261022c">
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme/crow-dark.svg?v=20261022c">
  <img src="docs/images/readme/crow-light.svg?v=20261022c" width="100%" alt="Crow v4.3.0: an agent, not a chat box. A local model at 200k context with 31 tools and MCP, memory, skills, goals, subagents, a browser panel, vision and a usage dashboard. It makes and edits images with Qwen-Image 2.1 beside crow-nest's 27B on one 32 GB card. Runs on this machine, on OpenRouter, or on your Claude subscription through Claude Code. crow-nest CNQ4.5-M on an RTX 5090, Windows, 2026-10-06: 40 tok/s decode in Crow at 8k, 780 tok/s prefill at 100k–175k.">
</picture>

**Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
```

**Image tools, Linux** (optional: builds sd-server, ~3 min)

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash -s -- --build-image-server
```

**Linux, one window** (Crow, the crow-nest engine and the operating points you pick; needs `gtk3`, `webkit2gtk-4.1`, `python-gobject`)

```bash
curl -fLO https://github.com/nibor1896/Crow/releases/download/v4.3.0/CrowSetup-linux-x64 && chmod +x CrowSetup-linux-x64 && ./CrowSetup-linux-x64
```

**Windows, one window** (Crow, the crow-nest engine and the operating points you pick)

```powershell
irm https://github.com/nibor1896/Crow/releases/latest/download/CrowSetup.exe -OutFile CrowSetup.exe; .\CrowSetup.exe
```

**Windows, Crow alone** (image server included in the package)

```powershell
irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1 | iex
```

**Claude subscription** (optional: Claude Code signs in, Crow never sees a token; then Settings → Model → Claude (subscription), or pick it in the operating-point window, [details](docs/user-guide/remote-models.md#claude-subscription))

```bash
npm install -g @anthropic-ai/claude-code && claude auth login
```

<p align="center">
<a href="docs/README.md#user-guide">User guide</a> ·
<a href="docs/README.md#reference">Reference</a> ·
<a href="docs/README.md#operating-points-and-measurements">Operating points and measurements</a> ·
<a href="docs/README.md#developer-guide">Developer guide</a> ·
<a href="docs/README.md#plans">Plans</a> ·
<a href="docs/README.md#archive">Archive</a>
</p>

<p align="center"><sub>
MIT · <a href="https://github.com/nibor1896/crow">nibor1896/crow</a> ·
Model: <a href="https://huggingface.co/nibor1896/Qwen3.8-Flash-Next-CNQ4.5-M">Qwen3.8-Flash-Next CNQ4.5-M</a> (Qwen Community License 1.0) ·
Model: <a href="https://huggingface.co/zai-org/GLM-5.3-Flash">GLM-5.3-Flash</a> (MIT) ·
Engine: <a href="https://github.com/nibor1896/crow-nest">crow-nest</a> ·
Images: <a href="https://huggingface.co/Qwen/Qwen-Image-2.1">Qwen-Image 2.1</a> (Qwen Research License, non-commercial) ·
GGUF line: <a href="https://huggingface.co/unsloth">Unsloth</a>, <a href="https://github.com/ggml-org/llama.cpp">llama.cpp</a>
</sub></p>

<p align="center">
<a href="https://ko-fi.com/nibor1896"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme/kofi-dark.svg">
  <img src="docs/images/readme/kofi-light.svg" height="44" alt="Support Crow on Ko-fi">
</picture></a>
</p>
