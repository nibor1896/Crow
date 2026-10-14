"""Tokens per category of a stored Crow session, and the #263 batch replayed on it (#359).

#263's scratch method, committed: a stored session file in, tokens per
category out (head, user, reasoning, assistant text, call arguments by tool,
results by tool), each in total and behind the keep window.

WHAT IT COUNTS, and the report names which one ran:

  rendered template   jinja2 importable and a chat_template.jinja beside the
                      tokenizer. The messages are rendered as transformers and
                      crow-nest serve render them (trim_blocks, lstrip_blocks,
                      loopcontrols, tojson = json.dumps with ensure_ascii off,
                      call arguments parsed to an object first, as serve's
                      `normalize_messages_as` does), then tokenised without
                      inserted special tokens.
  raw values          no jinja2, no template, or --raw: every string value of
                      the messages joined by blank lines. No template markup,
                      so it under-counts.

NOT IN EITHER COUNT: the request's tools block (a session file does not store
the tool schemas) and vision tokens. The session's recorded `context_tokens`
(the server's count) is printed beside the total for that reason.

PER CATEGORY BY DIFFERENCE: a category's tokens are the total minus the total
with that category's values emptied, so a merge across a boundary lands where
it belongs; what is left is the markup (role headers, tags, argument names).
"behind" empties only the messages behind the keep window, the cut
crow_core.clearable_results uses (the last 5 assistant messages are kept).

--replay forces the #263 batch with crow_core's own `clear_old_results`, keep
5, at a message index (--at, rounded up to the next assistant message; default
the start of the keep window). The conversation is the one the batch would
see: the stored messages up to the request before the round after the fifth
kept one. Two arms on that same conversation:

  results             `inputs=False`, the #263 batch
  results+calls       `inputs=True`, results plus call bodies (#359)

Per arm: what was cleared, tokens freed, the first changed message, the tokens
re-read from there (longest common token prefix, the server's rule) and the
re-prefill events (one batch is one, by construction). `render_stable` says
whether the rewritten arguments render exactly as the original arguments with
only the stubbed values swapped. `stub_tokens`: the call body stubs, counted.
The originals go to <temp>/context-breakdown-359, removed afterwards; every
count is taken with the stubs naming <SESSION_DIR>/cleared/<stamp>.json, the
file a live batch on this machine names.

--walk replays the history round by round under the LIVE rule, per arm: at
every point the turn loop calls `clear_before_roll` the window count is the
conversation as it stands (rendered through the last assistant message, plus
--offset for the tools block a session does not store), and crow_core decides
with its own share (0.65 at home) and `at_least` (0.10 of --n-ctx). Per arm:
every batch (where, the count, what was cleared, tokens freed, re-prefill
tokens), the re-prefill events, and where `should_roll` would roll. The count
is exact after a batch, where the live loop holds a low estimate until the
next usage block.

Usage:
  python tools/context_breakdown.py SESSION.json [--tokenizer PATH] [--raw] [--keep N] [--json]
  python tools/context_breakdown.py SESSION.json --replay [--at N] [--n-ctx N] [--json]
  python tools/context_breakdown.py SESSION.json --walk [--n-ctx N] [--offset N] [--json]

The default tokenizer follows the session's `model`: GLM-5.3-Flash or
Qwen3.8-Flash-Next under <crow-nest>/models/<name>-original/ (CROW_NEST, else
~/dev/crow-nest). A session that recorded no model needs --tokenizer.

Exit 0 = report written. 2 = setup (no tokenizer, unreadable session, a cut
inside the keep window).

A DEV TOOL. cli/ never imports it, so neither tokenizers nor jinja2 becomes a
dependency of Crow; it imports crow_core to replay the batch Crow ships.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOME = os.path.expanduser("~")
KEEP = 5
N_CTX = 200_000
# The originals file's name in a replay: a real stamp's length.
STAMP = "20261014-120000"
# (arm, inputs): #263's batch, and the same batch with the call bodies (#359)
ARMS = (("results", False), ("results+calls", True))
# (substring of the recorded model, lower case) -> crow-nest model folder
MODELS = (("glm", "GLM-5.3-Flash-original"),
          ("qwen", "Qwen3.8-Flash-Next-original"),
          ("flash-next", "Qwen3.8-Flash-Next-original"))


def crow_nest_dir() -> str:
    return os.environ.get("CROW_NEST") or os.path.join(HOME, "dev", "crow-nest")


def default_tokenizer(model):
    """The tokenizer.json for a recorded model name, or None."""
    name = (model or "").lower()
    for needle, folder in MODELS:
        if needle in name:
            return os.path.join(crow_nest_dir(), "models", folder, "tokenizer.json")
    return None


def shown(path) -> str:
    """A path for the report: the user profile as <home>, whichever
    separators the path was given with."""
    path = os.path.normpath(str(path))
    if HOME and path.lower().startswith(HOME.lower()):
        return "<home>" + path[len(HOME):]
    return path


def import_core():
    sys.path.insert(0, os.path.join(REPO, "cli"))
    import crow_core
    return crow_core


# ------------------------------------------------------------------ messages

def parse_args(raw) -> dict:
    """`arguments` as the template sees it: serve's `normalize_messages_as`.

    An object or a string that parses to one: that object. Empty or null: {}.
    Anything else: {"_raw": the text}, which serve shows verbatim.
    """
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return {"_raw": raw}
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        return {"_raw": raw}
    return {"_raw": json.dumps(raw)}


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text") or "" for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def result_names(messages) -> dict:
    """{index of a tool message: tool name}, by POSITION behind its call, as
    crow_core.clearable_results pairs them (call ids repeat across rounds)."""
    names, pending = {}, []
    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            pending = list(m.get("tool_calls") or [])
        elif role == "tool":
            call = pending.pop(0) if pending else {}
            names[i] = (call.get("function") or {}).get("name") or "tool"
        else:
            pending = []
    return names


def keep_cut(messages, keep=KEEP) -> int:
    """The first kept message: the last `keep` assistant messages (at least
    one) are kept. 0 when nothing is behind them."""
    keep = max(1, int(keep))
    rounds = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    return rounds[-keep] if len(rounds) > keep else 0


def categories(messages) -> list:
    tools = sorted({(c.get("function") or {}).get("name") or "tool"
                    for m in messages if m.get("role") == "assistant"
                    for c in m.get("tool_calls") or []})
    results = sorted(set(result_names(messages).values()))
    return (["head", "user", "reasoning", "assistant text"]
            + ["args " + t for t in tools] + ["results " + t for t in results])


def blank(messages, category, upto) -> list:
    """A copy of `messages` with `category`'s values emptied in messages[:upto]."""
    names = result_names(messages) if category.startswith("results ") else {}
    out = []
    for i, m in enumerate(messages):
        role = m.get("role")
        if i >= upto:
            out.append(m)
        elif category == "head" and role == "system":
            out.append(dict(m, content=""))
        elif category == "user" and role == "user":
            out.append(dict(m, content=""))
        elif category == "reasoning" and role == "assistant" and "reasoning_content" in m:
            out.append(dict(m, reasoning_content=""))
        elif category == "assistant text" and role == "assistant":
            out.append(dict(m, content=""))
        elif category.startswith("args ") and role == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = c.get("function") or {}
                if (fn.get("name") or "tool") == category[5:]:
                    emptied = {k: "" for k in parse_args(fn.get("arguments"))}
                    c = dict(c, function=dict(fn, arguments=json.dumps(emptied)))
                calls.append(c)
            out.append(dict(m, tool_calls=calls))
        elif category.startswith("results ") and role == "tool" and names.get(i) == category[8:]:
            out.append(dict(m, content=""))
        else:
            out.append(m)
    return out


def _values(messages, category, upto) -> int:
    """How many non-empty values the category holds in messages[:upto]; for
    call arguments, every argument value counts."""
    names = result_names(messages) if category.startswith("results ") else {}
    n = 0
    for i, m in enumerate(messages[:upto]):
        role = m.get("role")
        if category == "head" and role == "system":
            n += bool(_text(m.get("content")))
        elif category == "user" and role == "user":
            n += bool(_text(m.get("content")))
        elif category == "reasoning" and role == "assistant":
            n += bool(m.get("reasoning_content"))
        elif category == "assistant text" and role == "assistant":
            n += bool(_text(m.get("content")))
        elif category.startswith("args ") and role == "assistant":
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                if (fn.get("name") or "tool") == category[5:]:
                    n += sum(1 for v in parse_args(fn.get("arguments")).values()
                             if v not in ("", None))
        elif category.startswith("results ") and role == "tool" and names.get(i) == category[8:]:
            n += bool(_text(m.get("content")))
    return n


# ------------------------------------------------------------------ renderers

def raw_render(messages) -> str:
    """Every string value, in order, joined by blank lines. No markup."""
    parts = []
    for m in messages:
        parts.append(_text(m.get("content")))
        if isinstance(m.get("reasoning_content"), str):
            parts.append(m["reasoning_content"])
        for c in m.get("tool_calls") or []:
            for v in parse_args((c.get("function") or {}).get("arguments")).values():
                parts.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return "\n\n".join(p for p in parts if p)


def template_renderer(path):
    """render(messages) -> str with the chat template at `path`, as
    transformers' `apply_chat_template` and crow-nest serve set it up."""
    import jinja2
    from jinja2.ext import loopcontrols
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                        extensions=[loopcontrols])

    def tojson(value, ensure_ascii=False, indent=None, separators=None, sort_keys=False):
        return json.dumps(value, ensure_ascii=ensure_ascii, indent=indent,
                          separators=separators, sort_keys=sort_keys)

    def raise_exception(message):
        raise jinja2.exceptions.TemplateError(message)

    env.filters["tojson"] = tojson
    env.globals["raise_exception"] = raise_exception
    template = env.from_string(source)

    def render(messages):
        wire = []
        for m in messages:
            if m.get("tool_calls"):
                m = dict(m, tool_calls=[
                    dict(c, function=dict(c.get("function") or {}, arguments=parse_args(
                        (c.get("function") or {}).get("arguments"))))
                    for c in m["tool_calls"]])
            wire.append(m)
        return template.render(messages=wire, tools=None, documents=None,
                               add_generation_prompt=False)
    return render


def tokenizer_encoder(path):
    """encode(text) -> ids, with the model's own tokenizer.json."""
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(path)
    return lambda text: tok.encode(text, add_special_tokens=False).ids


# ------------------------------------------------------------------ the report

def breakdown(messages, encode, render, keep=KEEP) -> dict:
    cut = keep_cut(messages, keep)
    total = len(encode(render(messages)))
    rows = []
    for cat in categories(messages):
        whole = total - len(encode(render(blank(messages, cat, len(messages)))))
        behind = total - len(encode(render(blank(messages, cat, cut)))) if cut else 0
        rows.append({"category": cat, "tokens": whole, "behind": behind,
                     "values": _values(messages, cat, len(messages)),
                     "values_behind": _values(messages, cat, cut)})
    return {"total": total, "markup": total - sum(r["tokens"] for r in rows),
            "messages": len(messages), "keep": max(1, int(keep)), "cut": cut,
            "rows": rows}


def fire_window(messages, at=None, keep=KEEP):
    """(cut, end): the batch fires on messages[:end] and keeps from `cut` on."""
    keep = max(1, int(keep))
    rounds = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    if at is None:
        if len(rounds) <= keep:
            raise ValueError("no assistant message is behind the last %d" % keep)
        return rounds[-keep], len(messages)
    later = [r for r in rounds if r >= int(at)]
    if len(later) < keep:
        raise ValueError("message %d is inside the keep window: fewer than %d "
                         "assistant messages from there on" % (int(at), keep))
    return later[0], (later[keep] if len(later) > keep else len(messages))


def _common(a, b) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _swapped(conv, after) -> list:
    """`conv` with every changed argument value swapped in its PARSED object:
    what `after` must render as if the rewrite moved nothing else."""
    out = []
    for old, new in zip(conv, after):
        if old.get("role") != "assistant" or old.get("tool_calls") == new.get("tool_calls"):
            out.append(new if old.get("role") != "assistant" else old)
            continue
        calls = []
        for c_old, c_new in zip(old["tool_calls"], new["tool_calls"]):
            a_old = parse_args((c_old.get("function") or {}).get("arguments"))
            a_new = parse_args((c_new.get("function") or {}).get("arguments"))
            merged = {k: a_new.get(k, v) for k, v in a_old.items()}
            calls.append(dict(c_old, function=dict(c_old.get("function") or {},
                                                   arguments=merged)))
        out.append(dict(old, tool_calls=calls))
    return out


def _relocate(messages, path, real) -> list:
    """`messages` with the originals file `path` named `real` in every stub:
    in tool contents as written, in call arguments as JSON writes it."""
    if path == real:
        return messages
    quoted = (json.dumps(path, ensure_ascii=False)[1:-1],
              json.dumps(real, ensure_ascii=False)[1:-1])
    out = []
    for m in messages:
        if isinstance(m.get("content"), str) and path in m["content"]:
            m = dict(m, content=m["content"].replace(path, real))
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = c.get("function") or {}
                raw = fn.get("arguments")
                if isinstance(raw, str) and quoted[0] in raw:
                    c = dict(c, function=dict(fn, arguments=raw.replace(*quoted)))
                calls.append(c)
            m = dict(m, tool_calls=calls)
        out.append(m)
    return out


def _stub_values(before, after) -> list:
    """Every call body value `after` holds as a stub where `before` held text."""
    out = []
    for old, new in zip(before, after):
        if old.get("role") != "assistant" or old.get("tool_calls") == new.get("tool_calls"):
            continue
        for c_old, c_new in zip(old["tool_calls"], new["tool_calls"]):
            a_old = parse_args((c_old.get("function") or {}).get("arguments"))
            a_new = parse_args((c_new.get("function") or {}).get("arguments"))
            out += [v for k, v in a_new.items() if a_old.get(k) != v
                    and isinstance(v, str) and v.startswith("[cleared at ")]
    return out


def _batch(core, conv, tokens, n_ctx, path, real, **kw):
    """One crow_core batch on `conv`: (done, the messages after it, with the
    stubs naming `real` instead of the temp file `path`)."""
    talk = core.Conversation(None)
    talk.restore(conv)
    done = core.clear_old_results(talk, tokens, n_ctx, path=path, **kw)
    return done, _relocate(talk.payload(), path, real) if done else conv


def replay(messages, encode, render, at=None, keep=KEEP, n_ctx=N_CTX, core=None) -> dict:
    core = core or import_core()
    cut, end = fire_window(messages, at, keep)
    conv = [dict(m) for m in messages[:end]]
    ids0 = encode(render(conv))
    tmp = os.path.join(tempfile.gettempdir(), "context-breakdown-359")
    shutil.rmtree(tmp, ignore_errors=True)
    real = os.path.join(core.SESSION_DIR, "cleared", STAMP + ".json")
    arms, stable = {}, None
    try:
        for arm, inputs in ARMS:
            path = os.path.join(tmp, "r" if not inputs else "c", "cleared", STAMP + ".json")
            done, after = _batch(core, conv, max(1, len(ids0)), n_ctx, path, real,
                                 at=1e-9, keep_rounds=keep, at_least=0.0, inputs=inputs)
            ids1 = encode(render(after))
            first = next((i for i, (a, b) in enumerate(zip(conv, after)) if a != b), None)
            stubs = [len(encode(s)) for s in _stub_values(conv, after)]
            arms[arm] = {
                "results": done["results"] if done else 0,
                "call_bodies": done["calls"] if done else 0,
                "tokens_after": len(ids1),
                "freed": len(ids0) - len(ids1),
                "first_changed_message": first,
                "reprefill_tokens": len(ids1) - _common(ids0, ids1) if done else 0,
                "reprefill_events": 1 if done else 0,
                "estimate_typical": done["typical"] if done else 0,
                "estimate_low": done["freed"] if done else 0,
                "estimate_call_bodies": done["typical_calls"] if done else 0,
                "stub_tokens": {"n": len(stubs),
                                "mean": round(sum(stubs) / len(stubs), 1) if stubs else 0,
                                "min": min(stubs) if stubs else 0,
                                "max": max(stubs) if stubs else 0},
            }
            if inputs:
                stable = render(after) == render(_swapped(conv, after))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"cut": cut, "end": end, "keep": max(1, int(keep)), "n_ctx": n_ctx,
            "tokens_before": len(ids0), "originals_named": shown(real), "arms": arms,
            "bodies_on_top": arms["results+calls"]["freed"] - arms["results"]["freed"],
            "render_stable": stable}


def walk(messages, encode, render, keep=KEEP, n_ctx=N_CTX, offset=0, at=None,
         at_least=None, arms=None, core=None) -> dict:
    """The stored history replayed round by round under the live rule, per arm.

    At every point the turn loop calls `clear_before_roll` (before each
    assistant message: a turn's start or a tool round's end) the window count
    is the conversation as it stands then, rendered, through the last
    assistant message (the server's last usage: prompt plus answer), plus
    `offset`. crow_core's own `clear_old_results` decides with the endpoint
    default share and `at_least` (or the ones given); a batch rewrites the
    conversation for every later point. The arm stops where `should_roll`
    would roll. One difference to the live loop: after a batch the count is
    recounted here, where the live loop holds crow_core's low estimate until
    the next usage block.
    """
    core = core or import_core()
    rounds = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    share = core.context_clear_share(False) if at is None else at
    least = core.CONTEXT_CLEAR_AT_LEAST if at_least is None else at_least
    counted = {}

    def count(msgs):
        text = render(msgs)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key not in counted:
            counted[key] = len(encode(text))
        return counted[key]

    tmp = os.path.join(tempfile.gettempdir(), "context-breakdown-359-walk")
    shutil.rmtree(tmp, ignore_errors=True)
    out = {}
    try:
        for name, inputs in arms or ARMS:
            conv, batches, rolled = [dict(m) for m in messages], [], None
            for n in range(1, len(rounds)):
                k, last = rounds[n], rounds[n - 1]
                tokens = count(conv[:last + 1]) + offset
                stamp = "20261014-%06d.json" % k
                path = os.path.join(tmp, "c" if inputs else "r", "cleared", stamp)
                real = os.path.join(core.SESSION_DIR, "cleared", stamp)
                done, after = _batch(core, conv[:k], tokens, n_ctx, path, real,
                                     at=share, keep_rounds=keep, at_least=least,
                                     inputs=inputs)
                if done:
                    ids0, ids1 = encode(render(conv[:k])), encode(render(after))
                    batches.append({
                        "message": k, "context_tokens": tokens,
                        "results": done["results"], "call_bodies": done["calls"],
                        "first_changed_message": next(
                            (i for i, (a, b) in enumerate(zip(conv, after)) if a != b), None),
                        "freed": len(ids0) - len(ids1),
                        "reprefill_tokens": len(ids1) - _common(ids0, ids1),
                        "estimate_typical": done["typical"]})
                    conv = after + conv[k:]
                    tokens = count(conv[:last + 1]) + offset
                if core.should_roll(tokens, n_ctx):
                    rolled = k
                    break
            out[name] = {"batches": batches, "reprefill_events": len(batches),
                         "reprefill_tokens": sum(b["reprefill_tokens"] for b in batches),
                         "freed": sum(b["freed"] for b in batches),
                         "rolled_at": rolled,
                         "tokens_end": None if rolled is not None else count(conv) + offset}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"n_ctx": n_ctx, "at": share, "at_least": least, "keep": max(1, int(keep)),
            "offset": offset, "rollover_at": core.ROLLOVER_AT, "arms": out,
            "events_equal": len({a["reprefill_events"] for a in out.values()}) <= 1}


def _table(doc) -> str:
    b = doc["breakdown"]
    lines = ["session: %s" % doc["session"],
             "model: %s" % (doc["model"] or "not recorded"),
             "tokenizer: %s" % doc["tokenizer"],
             "mode: %s" % doc["mode"],
             "messages: %d; keep window: the last %d assistant messages, from message %d"
             % (b["messages"], b["keep"], b["cut"]),
             "recorded context_tokens: %s (the server's count, tools block included)"
             % ("{:,}".format(doc["recorded_context_tokens"])
                if isinstance(doc["recorded_context_tokens"], int) else "not recorded"),
             "",
             "| category | tokens | behind keep window | values | values behind |",
             "|---|---|---|---|---|"]
    for r in b["rows"]:
        lines.append("| %s | {:,} | {:,} | %d | %d |".format(r["tokens"], r["behind"])
                     % (r["category"], r["values"], r["values_behind"]))
    lines.append("| markup (by difference) | {:,} | | | |".format(b["markup"]))
    lines.append("| total | {:,} | {:,} | | |".format(
        b["total"], sum(r["behind"] for r in b["rows"])))
    rep = doc.get("replay")
    if rep:
        lines += ["",
                  "replay: batch at message %d (keep %d) on messages [0, %d), %s tokens before"
                  % (rep["cut"], rep["keep"], rep["end"], "{:,}".format(rep["tokens_before"])),
                  "",
                  "| arm | results | call bodies | tokens freed | first changed message "
                  "| re-prefill tokens | re-prefill events | crow_core estimate (typical / low) |",
                  "|---|---|---|---|---|---|---|---|"]
        for name in ("results", "results+calls"):
            a = rep["arms"][name]
            lines.append("| %s | %d | %d | {:,} | %s | {:,} | %d | {:,} / {:,} |".format(
                a["freed"], a["reprefill_tokens"], a["estimate_typical"], a["estimate_low"])
                % (name, a["results"], a["call_bodies"], a["first_changed_message"],
                   a["reprefill_events"]))
        stubs = rep["arms"]["results+calls"]["stub_tokens"]
        lines += ["",
                  "call bodies on top of the results: {:,} tokens".format(rep["bodies_on_top"]),
                  "call body stubs: n %d, tokens mean %s, min %d, max %d (naming %s)"
                  % (stubs["n"], stubs["mean"], stubs["min"], stubs["max"],
                     rep["originals_named"]),
                  "render stable (only the stubbed values moved): %s"
                  % ("yes" if rep["render_stable"] else "NO")]
    wk = doc.get("walk")
    if wk:
        lines += ["",
                  "walk: n_ctx {:,}, batch at {} with at_least {}, keep {}, count + {:,}, "
                  "rollover at {}".format(wk["n_ctx"], wk["at"], wk["at_least"], wk["keep"],
                                          wk["offset"], wk["rollover_at"]),
                  "",
                  "| arm | batch at message | window count | results | call bodies "
                  "| tokens freed | first changed message | re-prefill tokens |",
                  "|---|---|---|---|---|---|---|---|"]
        for name, a in wk["arms"].items():
            for b in a["batches"]:
                lines.append("| %s | %d | {:,} | %d | %d | {:,} | %s | {:,} |".format(
                    b["context_tokens"], b["freed"], b["reprefill_tokens"])
                    % (name, b["message"], b["results"], b["call_bodies"],
                       b["first_changed_message"]))
            if not a["batches"]:
                lines.append("| %s | none | | | | | | |" % name)
        lines += ["",
                  "| arm | re-prefill events | re-prefill tokens | tokens freed | rolls over at "
                  "| tokens at the end |",
                  "|---|---|---|---|---|---|"]
        for name, a in wk["arms"].items():
            lines.append("| %s | %d | {:,} | {:,} | %s | %s |".format(
                a["reprefill_tokens"], a["freed"])
                % (name, a["reprefill_events"],
                   "message %d" % a["rolled_at"] if a["rolled_at"] is not None else "no",
                   "{:,}".format(a["tokens_end"]) if a["tokens_end"] is not None else ""))
        lines += ["", "re-prefill events equal: %s" % ("yes" if wk["events_equal"] else "NO")]
    return "\n".join(lines)


def main(argv=None, encode=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--tokenizer", help="tokenizer.json (default: by the recorded model)")
    ap.add_argument("--raw", action="store_true", help="count raw values, no template")
    ap.add_argument("--keep", type=int, default=KEEP)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--at", type=int, default=None)
    ap.add_argument("--n-ctx", type=int, default=N_CTX)
    ap.add_argument("--walk", action="store_true",
                    help="the history round by round under the live rule")
    ap.add_argument("--offset", type=int, default=0,
                    help="tokens added to the walk's window count (the tools block)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        doc = load_session(args.session)
    except (OSError, ValueError) as exc:
        print("SETUP ERROR: %s" % exc, file=sys.stderr)
        return 2
    messages = doc["messages"]
    tokenizer = args.tokenizer or default_tokenizer(doc.get("model"))
    if encode is None:
        if not tokenizer:
            print("SETUP ERROR: the session records no model; pass --tokenizer",
                  file=sys.stderr)
            return 2
        if not os.path.isfile(tokenizer):
            print("SETUP ERROR: no tokenizer at %s" % tokenizer, file=sys.stderr)
            return 2
        encode = tokenizer_encoder(tokenizer)
    template = (os.path.join(os.path.dirname(tokenizer), "chat_template.jinja")
                if tokenizer else None)
    render, mode = raw_render, "raw values"
    if not args.raw and template and os.path.isfile(template):
        try:
            render = template_renderer(template)
            mode = "rendered template (%s)" % shown(template)
        except ImportError:
            pass
    out = {"session": shown(os.path.abspath(args.session)),
           "model": doc.get("model") or "", "tokenizer": shown(tokenizer or "injected"),
           "mode": mode, "recorded_context_tokens": doc.get("context_tokens"),
           "breakdown": breakdown(messages, encode, render, args.keep)}
    if args.replay:
        try:
            out["replay"] = replay(messages, encode, render, args.at, args.keep, args.n_ctx)
        except ValueError as exc:
            print("SETUP ERROR: %s" % exc, file=sys.stderr)
            return 2
    if args.walk:
        out["walk"] = walk(messages, encode, render, args.keep, args.n_ctx, args.offset)
    print(json.dumps(out, indent=1) if args.json else _table(out))
    return 0


def load_session(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or not isinstance(doc.get("messages"), list):
        raise ValueError("%s holds no message list" % path)
    return doc


if __name__ == "__main__":
    sys.exit(main())
