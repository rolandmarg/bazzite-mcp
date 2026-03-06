from __future__ import annotations

import json
import sys
import warnings

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

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
    return [name for state, name in STATE_NAMES.items() if ss.contains(state)]


def _geom(node):
    try:
        rect = node.get_extents(Atspi.CoordType.SCREEN)
        if rect.width > 0:
            return {"x": rect.x, "y": rect.y, "w": rect.width, "h": rect.height}
    except Exception:
        pass
    return None


def _actions(node):
    try:
        action_iface = node.get_action_iface()
        if action_iface:
            return [
                action_iface.get_action_name(index)
                for index in range(action_iface.get_n_actions())
            ]
    except Exception:
        pass
    return []


def _text(node):
    try:
        text_iface = node.get_text_iface()
        if text_iface:
            count = text_iface.get_character_count()
            if count > 0:
                return text_iface.get_text(0, min(count, 200))
    except Exception:
        pass
    return ""


def _value(node):
    try:
        value_iface = node.get_value_iface()
        if value_iface:
            return value_iface.get_current_value()
    except Exception:
        pass
    return None


def dump(node, depth=0, max_depth=6):
    if depth > max_depth or not node:
        return None
    try:
        role = node.get_role_name()
        name = node.get_name() or ""
        data = {"role": role}
        if name:
            data["name"] = name
        states = _states(node)
        if states:
            data["states"] = states
        geom = _geom(node)
        if geom:
            data["geom"] = geom
        actions = _actions(node)
        if actions:
            data["actions"] = actions
        text = _text(node)
        if text:
            data["text"] = text
        value = _value(node)
        if value is not None:
            data["value"] = value
        children = []
        for index in range(min(node.get_child_count(), 100)):
            child = dump(node.get_child_at_index(index), depth + 1, max_depth)
            if child:
                children.append(child)
        if children:
            data["children"] = children
        return data
    except Exception as exc:
        return {"error": str(exc)}


def find_app(name_query):
    desktop = Atspi.get_desktop(0)
    query = name_query.lower()
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        if not app:
            continue
        app_name = (app.get_name() or "").lower()
        if query in app_name:
            return app
        for win_index in range(app.get_child_count()):
            win = app.get_child_at_index(win_index)
            if win and query in (win.get_name() or "").lower():
                return app
    return None


def do_action_on(app, element_query, action_name):
    query = element_query.lower()

    def search(node, depth=0):
        if depth > 10 or not node:
            return None
        try:
            role = node.get_role_name() or ""
            name = (node.get_name() or "").lower()
            text = ""
            try:
                text_iface = node.get_text_iface()
                if text_iface and text_iface.get_character_count() > 0:
                    text = text_iface.get_text(
                        0, min(text_iface.get_character_count(), 200)
                    ).lower()
            except Exception:
                pass
            if query in name or query in role or query in text:
                action_iface = node.get_action_iface()
                if action_iface:
                    for index in range(action_iface.get_n_actions()):
                        if action_iface.get_action_name(index).lower() == action_name.lower():
                            ok = action_iface.do_action(index)
                            return {
                                "found": True,
                                "did_action": ok,
                                "element": {"role": role, "name": node.get_name() or ""},
                            }
            for index in range(min(node.get_child_count(), 100)):
                result = search(node.get_child_at_index(index), depth + 1)
                if result:
                    return result
        except Exception:
            pass
        return None

    for index in range(app.get_child_count()):
        win = app.get_child_at_index(index)
        result = search(win)
        if result:
            return result
    return None


def set_text_on(app, element_query, new_text):
    query = element_query.lower()

    def search(node, depth=0):
        if depth > 10 or not node:
            return None
        try:
            role = node.get_role_name() or ""
            name = (node.get_name() or "").lower()
            if query in name or query in role:
                editable_text_iface = node.get_editable_text_iface()
                if editable_text_iface:
                    text_iface = node.get_text_iface()
                    if text_iface:
                        old_len = text_iface.get_character_count()
                        if old_len > 0:
                            editable_text_iface.delete_text(0, old_len)
                        editable_text_iface.insert_text(0, new_text, len(new_text))
                        return {
                            "found": True,
                            "set": True,
                            "element": {"role": role, "name": node.get_name() or ""},
                        }
            for index in range(min(node.get_child_count(), 100)):
                result = search(node.get_child_at_index(index), depth + 1)
                if result:
                    return result
        except Exception:
            pass
        return None

    for index in range(app.get_child_count()):
        win = app.get_child_at_index(index)
        result = search(win)
        if result:
            return result
    return None


def main() -> None:
    cmd = json.loads(sys.argv[1])

    if cmd["op"] == "list_apps":
        desktop = Atspi.get_desktop(0)
        apps = []
        for index in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(index)
            if app:
                windows = []
                for win_index in range(app.get_child_count()):
                    win = app.get_child_at_index(win_index)
                    if win:
                        windows.append(win.get_name() or "")
                apps.append(
                    {
                        "name": app.get_name() or "(unnamed)",
                        "pid": app.get_process_id(),
                        "windows": windows,
                    }
                )
        print(json.dumps(apps))
        return

    if cmd["op"] == "inspect":
        app = find_app(cmd["query"])
        if not app:
            print(
                json.dumps(
                    {
                        "error": f"App not found: {cmd['query']}",
                        "hint": "App may not expose accessibility data. Use screenshot(target='window') for visual inspection.",
                    }
                )
            )
            return

        trees = []
        for index in range(app.get_child_count()):
            win = app.get_child_at_index(index)
            tree = dump(win, max_depth=cmd.get("depth", 6))
            if tree:
                trees.append(tree)
        print(
            json.dumps(
                {"app": app.get_name(), "pid": app.get_process_id(), "windows": trees}
            )
        )
        return

    if cmd["op"] == "do_action":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
            return
        result = do_action_on(app, cmd["element"], cmd["action"])
        if result:
            print(json.dumps(result))
            return
        print(
            json.dumps(
                {
                    "found": False,
                    "error": f"No element matching '{cmd['element']}' with action '{cmd['action']}'",
                }
            )
        )
        return

    if cmd["op"] == "set_text":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
            return
        result = set_text_on(app, cmd["element"], cmd["text"])
        if result:
            print(json.dumps(result))
            return
        print(
            json.dumps(
                {
                    "found": False,
                    "error": f"No editable element matching '{cmd['element']}'",
                }
            )
        )
        return

    print(json.dumps({"error": f"Unknown operation: {cmd['op']}"}))


if __name__ == "__main__":
    main()
