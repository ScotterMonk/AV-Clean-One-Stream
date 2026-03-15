from __future__ import annotations

import ast
import pprint
from pathlib import Path


class ConfigEditor:
    @staticmethod
    def load_gui_and_pipeline(config_path: Path) -> tuple[dict, dict, dict]:
        src = config_path.read_text(encoding="utf-8")
        mod = ast.parse(src)
        gui_val = None
        pipe_val = None
        qual_val = None
        for node in mod.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name == "GUI":
                    gui_val = ast.literal_eval(node.value)
                if name == "PIPELINE_CONFIG":
                    pipe_val = ast.literal_eval(node.value)
                if name == "QUALITY_PRESETS":
                    qual_val = ast.literal_eval(node.value)
        if not isinstance(gui_val, dict):
            raise ValueError("Could not find GUI dict in config.py")
        if not isinstance(pipe_val, dict):
            raise ValueError("Could not find PIPELINE_CONFIG dict in config.py")
        if not isinstance(qual_val, dict):
            raise ValueError("Could not find QUALITY_PRESETS dict in config.py")
        return gui_val, pipe_val, qual_val

    @staticmethod
    def load_gui_pipeline_quality_words(config_path: Path) -> tuple[dict, dict, dict, dict]:
        src = config_path.read_text(encoding="utf-8")
        mod = ast.parse(src)
        gui_val = None
        pipe_val = None
        qual_val = None
        words_val = None
        for node in mod.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name == "GUI":
                    gui_val = ast.literal_eval(node.value)
                if name == "PIPELINE_CONFIG":
                    pipe_val = ast.literal_eval(node.value)
                if name == "QUALITY_PRESETS":
                    qual_val = ast.literal_eval(node.value)
                if name == "WORDS_TO_REMOVE":
                    words_val = ast.literal_eval(node.value)
        if not isinstance(gui_val, dict):
            raise ValueError("Could not find GUI dict in config.py")
        if not isinstance(pipe_val, dict):
            raise ValueError("Could not find PIPELINE_CONFIG dict in config.py")
        if not isinstance(qual_val, dict):
            raise ValueError("Could not find QUALITY_PRESETS dict in config.py")
        if not isinstance(words_val, dict):
            raise ValueError("Could not find WORDS_TO_REMOVE dict in config.py")
        return gui_val, pipe_val, qual_val, words_val

    @staticmethod
    def write_gui_and_pipeline(
        config_path: Path,
        gui_dict: dict,
        pipeline_cfg: dict,
        quality_presets: dict,
        words_to_remove: dict | None = None,
    ) -> None:
        src = config_path.read_text(encoding="utf-8")
        lines = src.splitlines(keepends=True)
        mod = ast.parse(src)

        repls: list[tuple[int, int, str]] = []

        def mk_block(name: str, val: dict) -> str:
            body = pprint.pformat(val, width=100, sort_dicts=False)
            return f"{name} = {body}\n"

        for node in mod.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in {"GUI", "PIPELINE_CONFIG", "QUALITY_PRESETS", "WORDS_TO_REMOVE"}:
                    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
                        raise ValueError("Python did not provide AST line ranges for config.py")
                    start = int(node.lineno) - 1
                    end = int(node.end_lineno)
                    
                    val_to_write = None
                    if name == "GUI":
                        val_to_write = gui_dict
                    elif name == "PIPELINE_CONFIG":
                        val_to_write = pipeline_cfg
                    elif name == "QUALITY_PRESETS":
                        val_to_write = quality_presets
                    elif words_to_remove is not None:
                        val_to_write = words_to_remove
                    else:
                        continue
                         
                    new_text = mk_block(name, val_to_write)
                    repls.append((start, end, new_text))

        if not repls:
            raise ValueError("Could not locate config assignments to rewrite")

        repls.sort(key=lambda t: t[0], reverse=True)
        for start, end, new_text in repls:
            lines[start:end] = [new_text]

        config_path.write_text("".join(lines), encoding="utf-8")

