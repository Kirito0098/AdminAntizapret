from flask import jsonify, render_template, request, session, url_for

from core.services.edit_files import (
    build_edit_files_get_context,
    save_edit_file,
    validate_editor_content,
)


def register_edit_files_routes(
    app,
    *,
    auth_manager,
    file_editor,
    enqueue_background_task,
    task_run_doall,
    task_accepted_response,
    get_public_download_enabled,
):
    @app.route("/edit-files", methods=["GET", "POST"])
    @auth_manager.admin_required
    def edit_files():
        if request.method == "POST":
            file_type = request.form.get("file_type")
            content = request.form.get("content", "")
            content_ok, content_error = validate_editor_content(content)
            if not content_ok:
                return jsonify({"success": False, "message": content_error}), 400

            return save_edit_file(
                file_type,
                content,
                file_editor=file_editor,
                enqueue_background_task=enqueue_background_task,
                task_run_doall=task_run_doall,
                task_accepted_response=task_accepted_response,
                created_by_username=session.get("username"),
            )

        return render_template(
            "edit_files.html",
            **build_edit_files_get_context(
                file_editor,
                get_public_download_enabled,
                url_for,
            ),
        )
