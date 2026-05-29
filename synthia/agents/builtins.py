import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx

_BASH_TIMEOUT = 600
_MAX_OUTPUT = 30_000
_MAX_FETCH = 100_000


def create_builtin_tools(cwd: str | Path | None = None) -> list[Callable]:
    base = Path(cwd) if cwd else Path.cwd()

    def _resolve(path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else base / p

    async def run_bash(command: str) -> str:
        """Run a shell command and return its combined stdout/stderr output. Use this to execute
        scripts, inspect the filesystem, run CLI tools, or perform any shell operation.

        Args:
            command: The shell command to execute.
        """
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(base),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_BASH_TIMEOUT)
            output = stdout.decode(errors="replace")
            if len(output) > _MAX_OUTPUT:
                output = output[:_MAX_OUTPUT] + "\n... [output truncated]"
            return output or f"(exit code {proc.returncode}, no output)"
        except TimeoutError:
            return f"Error: command timed out after {_BASH_TIMEOUT}s"
        except Exception as error:
            return f"Error running command: {error}"

    async def read_file(path: str) -> str:
        """Read and return the contents of a file.

        Args:
            path: Absolute path, or path relative to the working directory.
        """
        try:
            return _resolve(path).read_text()
        except Exception as error:
            return f"Error reading file: {error}"

    async def write_file(path: str, content: str) -> str:
        """Write content to a file, creating parent directories as needed. Overwrites any existing file.

        Args:
            path: Absolute path, or path relative to the working directory.
            content: The full content to write.
        """
        try:
            target = _resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return f"Wrote {len(content)} bytes to {target}"
        except Exception as error:
            return f"Error writing file: {error}"

    async def fetch_url(url: str) -> str:
        """Fetch the contents of a URL over HTTP(S) and return the response body as text.

        Args:
            url: The fully-qualified URL to fetch.
        """
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as http:
                response = await http.get(url)
                text = response.text
                if len(text) > _MAX_FETCH:
                    text = text[:_MAX_FETCH] + "\n... [content truncated]"
                return text
        except Exception as error:
            return f"Error fetching URL: {error}"

    return [run_bash, read_file, write_file, fetch_url]
