from __future__ import annotations

import json
import subprocess
from textwrap import dedent

from mcp.server.fastmcp.exceptions import ToolError

_SYSTEM_PYTHON = "/usr/bin/python3"

_ATSPI_HELPER = dedent("""\
    import gi, json, sys
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    Atspi.init()

    STATE_NAMES = {
        Atspi.StateType.FOCUSED: "focused",
        Atspi.StateType.VISIBLE: "visible",
        Atspi.StateType.SHOWING: "showing",
        Atspi.StateType.ENABLED: "enabled",
        Atspi.StateType.CHECKED: "checked",
        Atspi.StateType.SELECTED: "selected",
        Atspi.StateType.EDITABLE: "editable",
        Atspi.StateType.ACTIVE: "active",
        Atspi.StateType.EXPANDABLE: "expandable",
        Atspi.StateType.EXPANDED: "expanded",
        Atspi.StateType.SENSITIVE: "sensitive",
    }

    def _states(node):
        ss = node.get_state_set()
        return [n for s, n in STATE_NAMES.items() if ss.contains(s)]

    def _geom(node):
        try:
            r = node.get_extents(Atspi.CoordType.SCREEN)
            if r.width > 0:
                return {"x": r.x, "y": r.y, "w": r.width, "h": r.height}
        except Exception:
            pass
        return None

    def _actions(node):
        try:
            ai = node.get_action_iface()
            if ai:
                return [ai.get_action_name(i) for i in range(ai.get_n_actions())]
        except Exception:
            pass
        return []

    def _text(node):
        try:
            ti = node.get_text_iface()
            if ti:
                n = ti.get_character_count()
                if n > 0:
                    return ti.get_text(0, min(n, 200))
        except Exception:
            pass
        return ""

    def _value(node):
        try:
            vi = node.get_value_iface()
            if vi:
                return vi.get_current_value()
        except Exception:
            pass
        return None

    def dump(node, depth=0, max_depth=6):
        if depth > max_depth or not node:
            return None
        try:
            role = node.get_role_name()
            name = node.get_name() or ""
            d = {"role": role}
            if name:
                d["name"] = name
            st = _states(node)
            if st:
                d["states"] = st
            g = _geom(node)
            if g:
                d["geom"] = g
            acts = _actions(node)
            if acts:
                d["actions"] = acts
            txt = _text(node)
            if txt:
                d["text"] = txt
            val = _value(node)
            if val is not None:
                d["value"] = val
            kids = []
            for i in range(min(node.get_child_count(), 100)):
                c = dump(node.get_child_at_index(i), depth + 1, max_depth)
                if c:
                    kids.append(c)
            if kids:
                d["children"] = kids
            return d
        except Exception as e:
            return {"error": str(e)}

    def find_app(name_query):
        desktop = Atspi.get_desktop(0)
        q = name_query.lower()
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if not app:
                continue
            app_name = (app.get_name() or "").lower()
            if q in app_name:
                return app
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                if win and q in (win.get_name() or "").lower():
                    return app
        return None

    def do_action_on(app, element_query, action_name):
        q = element_query.lower()
        def search(node, depth=0):
            if depth > 10 or not node:
                return None
            try:
                role = node.get_role_name() or ""
                name = (node.get_name() or "").lower()
                txt = ""
                try:
                    ti = node.get_text_iface()
                    if ti and ti.get_character_count() > 0:
                        txt = ti.get_text(0, min(ti.get_character_count(), 200)).lower()
                except Exception:
                    pass
                if q in name or q in role or q in txt:
                    ai = node.get_action_iface()
                    if ai:
                        for i in range(ai.get_n_actions()):
                            if ai.get_action_name(i).lower() == action_name.lower():
                                ok = ai.do_action(i)
                                return {"found": True, "did_action": ok,
                                        "element": {"role": role, "name": node.get_name() or ""}}
                for i in range(min(node.get_child_count(), 100)):
                    result = search(node.get_child_at_index(i), depth + 1)
                    if result:
                        return result
            except Exception:
                pass
            return None

        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            result = search(win)
            if result:
                return result
        return None

    def set_text_on(app, element_query, new_text):
        q = element_query.lower()
        def search(node, depth=0):
            if depth > 10 or not node:
                return None
            try:
                role = node.get_role_name() or ""
                name = (node.get_name() or "").lower()
                if q in name or q in role:
                    eti = node.get_editable_text_iface()
                    if eti:
                        ti = node.get_text_iface()
                        if ti:
                            old_len = ti.get_character_count()
                            if old_len > 0:
                                eti.delete_text(0, old_len)
                            eti.insert_text(0, new_text, len(new_text))
                            return {"found": True, "set": True,
                                    "element": {"role": role, "name": node.get_name() or ""}}
                for i in range(min(node.get_child_count(), 100)):
                    result = search(node.get_child_at_index(i), depth + 1)
                    if result:
                        return result
            except Exception:
                pass
            return None

        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            result = search(win)
            if result:
                return result
        return None

    cmd = json.loads(sys.argv[1])

    if cmd["op"] == "list_apps":
        desktop = Atspi.get_desktop(0)
        apps = []
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                windows = []
                for j in range(app.get_child_count()):
                    win = app.get_child_at_index(j)
                    if win:
                        windows.append(win.get_name() or "")
                apps.append({
                    "name": app.get_name() or "(unnamed)",
                    "pid": app.get_process_id(),
                    "windows": windows,
                })
        print(json.dumps(apps))

    elif cmd["op"] == "inspect":
        app = find_app(cmd["query"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['query']}",
                              "hint": "App may not expose accessibility data. Use screenshot(target='window') for visual inspection."}))
        else:
            trees = []
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                t = dump(win, max_depth=cmd.get("depth", 6))
                if t:
                    trees.append(t)
            print(json.dumps({"app": app.get_name(), "pid": app.get_process_id(),
                              "windows": trees}))

    elif cmd["op"] == "do_action":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
        else:
            result = do_action_on(app, cmd["element"], cmd["action"])
            if result:
                print(json.dumps(result))
            else:
                print(json.dumps({"found": False,
                    "error": f"No element matching '{cmd['element']}' with action '{cmd['action']}'"}))

    elif cmd["op"] == "set_text":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
        else:
            result = set_text_on(app, cmd["element"], cmd["text"])
            if result:
                print(json.dumps(result))
            else:
                print(json.dumps({"found": False,
                    "error": f"No editable element matching '{cmd['element']}'"}))
""")


def _atspi_call(cmd: dict) -> dict:
    """Call the AT-SPI helper via system Python and return parsed JSON."""
    result = subprocess.run(
        [_SYSTEM_PYTHON, "-c", _ATSPI_HELPER, json.dumps(cmd)],
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise ToolError(f"AT-SPI query failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ToolError(f"AT-SPI returned invalid JSON: {result.stdout[:200]}")


def interact(
    window: str,
    element: str,
    action: str = "Press",
) -> str:
    """Perform an action on a UI element via AT-SPI accessibility API."""
    result = _atspi_call(
        {
            "op": "do_action",
            "app": window,
            "element": element,
            "action": action,
        }
    )

    if result.get("error"):
        raise ToolError(result["error"])

    if result.get("found") and result.get("did_action"):
        element_info = result.get("element", {})
        return f"Performed '{action}' on {element_info.get('role', '?')}: \"{element_info.get('name', element)}\""

    raise ToolError(
        f"Action '{action}' failed on element '{element}'. "
        "Use manage_windows(action='inspect') to check available elements and actions."
    )


def set_text(window: str, element: str, text: str) -> str:
    """Set text content of an editable field via AT-SPI."""
    result = _atspi_call(
        {
            "op": "set_text",
            "app": window,
            "element": element,
            "text": text,
        }
    )

    if result.get("error"):
        raise ToolError(result["error"])

    if result.get("found") and result.get("set"):
        element_info = result.get("element", {})
        return f'Set text on {element_info.get("role", "?")}: "{element_info.get("name", element)}"'

    raise ToolError(f"Could not set text on element '{element}'.")
