<picture>
  <source media="(max-width: 700px) and (prefers-color-scheme: dark)" srcset="docs/images/readme/crow-mobile-dark.svg">
  <source media="(max-width: 700px)" srcset="docs/images/readme/crow-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme/crow-dark.svg">
  <img src="docs/images/readme/crow-light.svg" width="100%" alt="Crow: an agent, not a chat box. A local model at 200k context with 31 tools and MCP, memory, skills, goals, subagents, a browser panel and vision. It makes and edits images with Qwen-Image 2.1 beside crow-nest's 27B on one 32 GB card. Default engine crow-nest (Rust), 35.8 tok/s decode at 122k context on Linux.">
</picture>

**Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash
```

**Image tools, Linux** (optional: builds sd-server, ~3 min)

```bash
curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh | bash -s -- --build-image-server
```

**Windows, one window** (Crow, the crow-nest engine and the operating points you pick)

```powershell
irm https://github.com/nibor1896/Crow/releases/latest/download/CrowSetup.exe -OutFile CrowSetup.exe; .\CrowSetup.exe
```

**Windows, Crow alone** (image server included in the package)

```powershell
irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1 | iex
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
