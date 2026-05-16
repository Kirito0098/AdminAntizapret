from flask import jsonify


def save_edit_file(
    file_type,
    content,
    *,
    file_editor,
    enqueue_background_task,
    task_run_doall,
    task_accepted_response,
    created_by_username=None,
):
    if not file_editor.update_file_content(file_type, content):
        return jsonify({"success": False, "message": "Неверный тип файла."}), 400

    try:
        task = enqueue_background_task(
            "run_doall",
            task_run_doall,
            created_by_username=created_by_username,
            queued_message="Применение изменений запущено в фоне",
        )
        return task_accepted_response(
            task,
            "Файл сохранен. Применение изменений выполняется в фоне.",
        )
    except (RuntimeError, ValueError, OSError) as e:
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500
