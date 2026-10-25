from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class _Unset:
    """Sentinel distinguishing 'no system-prompt override' from an explicit ``None``."""


_UNSET = _Unset()


@dataclass(frozen=True)
class _SystemPrompt:
    """A system-prompt block source: literal ``text`` or a file ``path``."""

    text: str | None = None
    path: str | None = None

    def read(self) -> str:
        if self.text is not None:
            return self.text
        assert self.path is not None
        file = Path(self.path).expanduser()
        if not file.exists():
            raise FileNotFoundError(f"System prompt file not found: {self.path}")
        return file.read_text()

    @classmethod
    def one_of(cls, path: str | None, prompt: str | None) -> "_SystemPrompt":
        if (path is None) == (prompt is None):
            raise ValueError("Specify exactly one of 'path' or 'prompt'")
        if prompt is not None:
            return cls(text=prompt)
        assert path is not None
        return cls(path=str(Path(path).expanduser()))


class SystemPromptMixin:
    """Base system-prompt override plus appended user-guidance blocks."""

    _system_prompt: _SystemPrompt | None | _Unset
    _appended_prompts: list[_SystemPrompt]

    def set_system_prompt(self, path: str | None = None, prompt: str | None = None) -> None:
        """Override — or disable — the default (generalist) base system prompt.

        - ``set_system_prompt(prompt="...")`` — use ``prompt`` verbatim.
        - ``set_system_prompt(path="...")`` — read from a file (``~`` expanded;
          read lazily so the file need not exist at import).
        - ``set_system_prompt()`` — disable the base prompt entirely.

        Pass at most one of ``path`` / ``prompt``.
        """
        if path is not None and prompt is not None:
            raise ValueError("Specify at most one of 'path' or 'prompt'")
        if path is None and prompt is None:
            self._system_prompt = None
        else:
            self._system_prompt = _SystemPrompt.one_of(path, prompt)

    def resolve_system_prompt(self, default: str) -> str | None:
        """``default`` when no override is set, the override text when one is,
        or ``None`` when the base prompt was explicitly disabled."""
        override = self._system_prompt
        if isinstance(override, _Unset):
            return default
        return override.read() if override else None

    def append_system_prompt(self, path: str | None = None, prompt: str | None = None) -> None:
        """Append user-level, cross-project guidance after the base prompt.

        Keeps the base prompt intact; may be called multiple times and blocks
        are emitted in registration order. Pass exactly one of ``path``
        (``~`` expanded; read lazily per session) or ``prompt``.
        """
        self._appended_prompts.append(_SystemPrompt.one_of(path, prompt))

    def resolve_appended_prompts(self) -> list[str]:
        return [p.read() for p in self._appended_prompts]
