import io

import qrcode
from qrcode.exceptions import DataOverflowError
from qrcode.image.pil import PilImage


class QRGenerator:
    def __init__(self):
        pass

    def generate_qr_code(self, config_text):
        # Для длинных конфигов сначала пробуем высокий уровень коррекции,
        # затем снижаем его, чтобы поместить данные в максимально допустимую версию QR (40).
        correction_levels = (
            qrcode.constants.ERROR_CORRECT_H,
            qrcode.constants.ERROR_CORRECT_Q,
            qrcode.constants.ERROR_CORRECT_M,
            qrcode.constants.ERROR_CORRECT_L,
        )

        qr = None
        last_error = None
        for correction_level in correction_levels:
            try:
                candidate = qrcode.QRCode(
                    version=None,
                    error_correction=correction_level,
                    box_size=10,
                    border=4,
                )
                candidate.add_data(config_text)
                candidate.make(fit=True)
                qr = candidate
                break
            except (DataOverflowError, ValueError) as e:
                last_error = e

        if qr is None:
            raise ValueError(f"Конфигурация слишком длинная для QR-кода: {last_error}")

        img = qr.make_image(
            fill_color="black", back_color="white", image_factory=PilImage
        )

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        return img_byte_arr

    def generate_qr_for_download_url(self, download_url):
        """Генерирует QR с URL скачивания как fallback для слишком длинных конфигов."""
        return self.generate_qr_code(download_url)
