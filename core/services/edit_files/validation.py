def validate_editor_content(content) -> tuple[bool, str]:
    value = content or ""
    if "\x00" in value:
        return False, "Содержимое файла содержит недопустимый нулевой байт"
    if len(value.encode("utf-8")) > 1024 * 1024:
        return False, "Содержимое файла превышает допустимый размер 1 MiB"
    return True, ""
