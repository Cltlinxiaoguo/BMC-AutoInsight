"""极简 Jinja2 子集（pip 不可用时 fallback）."""
import re
from typing import Any, Dict

_FOR = re.compile(r"\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%\}(.*?)\{%\s*endfor\s*%\}", re.DOTALL)
_VAR = re.compile(r"\{\{\s*(\w+(?:\.\w+)*)\s*\}\}")

class Template:
    def __init__(self, source: str):
        self.source = source

    def render(self, **ctx: Any) -> str:
        out = self.source
        for m in _FOR.finditer(self.source):
            item, seq_name, block = m.group(1), m.group(2), m.group(3)
            seq = ctx.get(seq_name) or []
            parts = []
            for el in seq:
                local = dict(ctx)
                if isinstance(el, dict):
                    local[item] = el
                    for k, v in el.items():
                        local[k] = v
                else:
                    local[item] = el
                parts.append(_render_vars(block, local))
            out = out.replace(m.group(0), "".join(parts))
        return _render_vars(out, ctx)

def _render_vars(text: str, ctx: Dict[str, Any]) -> str:
    def repl(m):
        key = m.group(1)
        cur: Any = ctx
        for part in key.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part, "")
            else:
                cur = getattr(cur, part, "")
        return str(cur if cur is not None else "")
    return _VAR.sub(repl, text)
