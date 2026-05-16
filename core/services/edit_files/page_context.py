from .editor_metadata import get_editor_subtitle
from .file_groups import resolve_file_nav_group
from .route_actions import build_route_download_actions


def _fallback_title(file_type: str) -> str:
    return file_type.replace("_", " ").replace("-", " ").title()


def build_edit_files_get_context(file_editor, get_public_download_enabled, url_for) -> dict:
    file_contents = file_editor.get_file_contents()
    file_display_titles = file_editor.get_file_display_titles()
    public_download_enabled = get_public_download_enabled()

    file_nav_items = []
    editor_forms = []

    for index, (file_type, content) in enumerate(file_contents.items()):
        title = file_display_titles.get(file_type, _fallback_title(file_type))
        group = resolve_file_nav_group(file_type)
        is_active = index == 0

        file_nav_items.append(
            {
                "file_type": file_type,
                "group": group,
                "title": title,
                "is_active": is_active,
            }
        )

        editor_forms.append(
            {
                "file_type": file_type,
                "group": group,
                "title": title,
                "is_active": is_active,
                "content": content,
                "subtitle": get_editor_subtitle(file_type),
                "form_id": f"form-{file_type}",
            }
        )

    return {
        "file_nav_items": file_nav_items,
        "editor_forms": editor_forms,
        "route_actions": build_route_download_actions(public_download_enabled, url_for),
        "public_download_enabled": public_download_enabled,
    }
