"""Utilitário para leitura da versão da aplicação a partir do pyproject.toml."""

from functools import lru_cache
from pathlib import Path
import tomllib


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Retorna a versão declarada no pyproject.toml."""
    pyproject_path = Path(__file__).resolve().parent / "pyproject.toml"

    try:
        with pyproject_path.open("rb") as pyproject_file:
            data = tomllib.load(pyproject_file)
    except OSError:
        return "desconhecida"
    except tomllib.TOMLDecodeError:
        return "desconhecida"

    project_version = data.get("project", {}).get("version")
    if project_version:
        return str(project_version)

    poetry_version = data.get("tool", {}).get("poetry", {}).get("version")
    if poetry_version:
        return str(poetry_version)

    return "desconhecida"
