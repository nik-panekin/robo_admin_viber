import sys
import time
import logging

import keyboard

from startup_config import setup_logging
from viber_bot import ViberBot

HOTKEY_PAUSE = 'ctrl+alt+F12'
HOTKEY_TERMINATE = 'ctrl+alt+F10'
HOTKEY_ESC = 'esc'

APP_LOOP_DELAY = 2.0

FATAL_ERROR_STR = 'Критическая ошибка при выполнении программы.'

class Application():
    def __init__(self):
        setup_logging()
        logging.info('Запуск программы.')

        self.paused = False
        self.should_close = False
        self.bot = ViberBot()

        if not self.bot.connect():
            self.close()

        keyboard.add_hotkey(HOTKEY_ESC, self.close_query)

        try:
            while not self.bot.set_focus():
                if self.should_close:
                    self.close()

                logging.info(
                    'Выдвиньте окно приложения Viber на передний план вручную '
                    + f"или нажмите '{HOTKEY_ESC.upper()}' "
                    'для останова программы.'
                )
        except Exception:
            logging.exception(FATAL_ERROR_STR)
            self.close()

        keyboard.remove_hotkey(HOTKEY_ESC)

        keyboard.add_hotkey(HOTKEY_PAUSE, self.toggle_pause)
        keyboard.add_hotkey(HOTKEY_TERMINATE, self.close_query)

    def close(self):
        logging.info('Завершение работы программы.')
        keyboard.unhook_all()
        sys.exit()

    def close_query(self):
        logging.info('Получен запрос на закрытие программы. '
                     'Подождите завершения цикла.')
        self.should_close = True

    def toggle_pause(self):
        self.paused = not self.paused

        if self.paused:
            logging.info('Получен запрос на приостановку работы программы. '
                         'Подождите завершения цикла.')
        else:
            logging.info('Работа программы возобновлена.')

    def run(self):
        logging.info(
            'Запуск цикла автоматической модерации. Для выхода нажмите '
            + f"'{HOTKEY_TERMINATE.upper()}'. Для паузы/возобновления нажмите "
            + f"'{HOTKEY_PAUSE.upper()}'.")

        while True:
            if self.should_close:
                self.close()

            if self.paused:
                time.sleep(APP_LOOP_DELAY)
                continue

            try:
                if not self.bot.execute_moderation():
                    logging.error(FATAL_ERROR_STR)
                    self.close()
            except Exception:
                logging.error(FATAL_ERROR_STR)
                self.close()

            time.sleep(APP_LOOP_DELAY)

if __name__ == '__main__':
    Application().run()
