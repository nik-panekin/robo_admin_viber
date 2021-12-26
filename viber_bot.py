import time
import logging

import PIL.Image
import PIL.ImageGrab
from PIL.Image import Image
from pywinauto.application import Application, AppNotConnected
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError
from pywinauto import mouse, keyboard

from screen_reader import ScreenReader

VIBER_TITLE = 'Viber'

CHAT_LEFT = 300
CHAT_TOP = 112
CHAT_LEFT_PADDING = 40
CHAT_TOP_PADDING = 40
CHAT_RIGHT_PADDING = 10
CHAT_BOTTOM_PADDING = 50
CHAT_SAFE_PADDING = 5

MENU_WIDTH = 186
MENU_HEIGHT = 456
MENU_ITEM_TEXT = 'Удалить'

DEL_CONFIRM_WIDTH = 380
DEL_CONFIRM_HEIGHT = 180
DEL_CONFIRM_TEXT = 'сообщение будет удалено'

POPUP_DELAY = 1.0

SCROLL_PAGE_NUMBER = 5
SCROLL_BACK = -2

IMAGES_FOLDER = './img'
SCROLL_DOWN_IMAGE = f'{IMAGES_FOLDER}/down_arrow.png'

class ViberBot():
    def __init__(self):
        self.viber = None
        self.old_chat_screenshot = None
        self.reader = ScreenReader()
        self.scroll_down_image = PIL.Image.open(SCROLL_DOWN_IMAGE)

    def connect(self) -> bool:
        try:
            app = Application(backend='uia', allow_magic_lookup=True)
            app.connect(title=VIBER_TITLE)
        except (AppNotConnected, ElementNotFoundError):
            logging.error('Не удаётся подключиться к приложению Viber.')
            return False

        try:
            self.viber = app.window(title=VIBER_TITLE)
        except ElementNotFoundError:
            logging.error('Окно приложения Viber не найдено.')
            return False

        return True

    def get_screenshot(self) -> Image:
        if self.viber is None:
            return None

        return self.viber.capture_as_image()

    def get_chat_screenshot(self) -> Image:
        screenshot = self.get_screenshot()
        if screenshot is None:
            return None

        width, height = screenshot.size

        left = CHAT_LEFT + CHAT_LEFT_PADDING
        top = CHAT_TOP + CHAT_TOP_PADDING
        right = width - CHAT_RIGHT_PADDING
        bottom = height - CHAT_BOTTOM_PADDING

        return screenshot.crop((left, top, right, bottom))

    def get_del_confirm_screenshot(self) -> Image:
        screenshot = self.get_screenshot()
        if screenshot is None:
            return None

        width, height = screenshot.size

        left = (width // 2) - (DEL_CONFIRM_WIDTH // 2)
        top = (height // 2) - (DEL_CONFIRM_HEIGHT // 2)
        right = (width // 2) + (DEL_CONFIRM_WIDTH // 2)
        bottom = (height // 2) + (DEL_CONFIRM_HEIGHT // 2)

        return screenshot.crop((left, top, right, bottom))

    def get_menu_screenshot(self, x: int, y: int) -> Image:
        screenshot = PIL.ImageGrab.grab()

        width, height = screenshot.size

        left = max(x - MENU_WIDTH, 0)
        top = max(y - MENU_HEIGHT, 0)
        right = min(x + MENU_WIDTH, width)
        bottom = min(y + MENU_HEIGHT, height)

        return screenshot.crop((left, top, right, bottom))

    def set_focus(self) -> bool:
        if self.viber is None:
            return False

        self.viber.set_focus()

        try:
            self.viber.wait(wait_for='active')
        except TimeoutError:
            logging.error('Не удаётся передать фокус ввода '
                          'окну приложения Viber.')
            return False

        return True

    def scroll_down(self) -> bool:
        if not self.set_focus():
            return False

        button = self.reader.find_template(self.get_screenshot(),
                                           self.scroll_down_image)
        if button is None:
            return True

        win_rect = self.viber.rectangle()

        coords = (win_rect.left + (button['left'] + button['right']) // 2,
                  win_rect.top + (button['top'] + button['bottom']) // 2)

        mouse.move(coords=coords)
        mouse.click(coords=coords)

        return True

    def scroll_up(self) -> bool:
        if not self.set_focus():
            return False

        win_rect = self.viber.rectangle()

        coords = (
            win_rect.left + CHAT_LEFT + CHAT_SAFE_PADDING,
            (win_rect.top + win_rect.bottom) // 2
        )

        mouse.move(coords=coords)
        mouse.click(coords=coords)
        keyboard.send_keys('{PGUP}')
        mouse.scroll(coords=coords, wheel_dist=SCROLL_BACK)

        return True

    def chat_changed(self) -> bool:
        if not self.scroll_down():
            return None

        new_chat_screenshot = self.get_chat_screenshot()

        if ((self.old_chat_screenshot is None)
            or (not self.reader.identical_images(self.old_chat_screenshot,
                                                 new_chat_screenshot))):
            self.old_chat_screenshot = new_chat_screenshot
            return True

        return False

    def delete_post(self, x: int, y: int) -> bool:
        mouse.move(coords=(x, y))
        mouse.click(button='right', coords=(x, y))
        time.sleep(POPUP_DELAY)

        self.reader.set_image(self.get_menu_screenshot(x, y))
        self.reader.set_langs(['rus'])
        words = self.reader.get_words()
        if words is None:
            return False

        found = False
        for word in words:
            if word['text'] == MENU_ITEM_TEXT:
                found = True

                item_x = (max(x - MENU_WIDTH, 0)
                          + (word['left'] + word['right']) // 2)
                item_y = (max(y - MENU_HEIGHT, 0)
                          + (word['top'] + word['bottom']) // 2)

                mouse.move(coords=(item_x, item_y))
                mouse.click(coords=(item_x, item_y))
                time.sleep(POPUP_DELAY)

                del_confirm_screenshot = self.get_del_confirm_screenshot()
                if del_confirm_screenshot is None:
                    return False

                self.reader.set_image(del_confirm_screenshot)
                self.reader.set_langs(['rus'])
                text = self.reader.get_string()
                if (text is None) or (DEL_CONFIRM_TEXT not in text):
                    logging.error('Не найдено окно подтверждения удаления.')
                    return False

                keyboard.send_keys('{ENTER}')

                break

        if not found:
            logging.error(f'Не найден пункт меню "{MENU_ITEM_TEXT}".')
            return False

        return True

    def execute_moderation(self) -> bool:
        chat_changed = self.chat_changed()

        if chat_changed is None:
            return False
        elif chat_changed == False:
            return True

        logging.info('Чат изменился. Поиск сообщений с web-ссылками.')

        i = 0
        while i < SCROLL_PAGE_NUMBER:
            self.reader.set_image(self.get_chat_screenshot())
            self.reader.set_langs(['eng'])
            url = self.reader.locate_url()
            if url:
                logging.info(f"Обнаружена web-ссылка [{url['url']}].")
                win_rect = self.viber.rectangle()

                x = (win_rect.left + CHAT_LEFT + CHAT_LEFT_PADDING +
                        (url['left'] + url['right']) // 2)
                y = (win_rect.top + CHAT_TOP + CHAT_TOP_PADDING +
                        (url['top'] + url['bottom']) // 2)

                if self.delete_post(x, y):
                    logging.info(f"Сообщение со ссылкой [{url['url']}] "
                                 'удалено.')
                    continue
                else:
                    return False

            if i < SCROLL_PAGE_NUMBER - 1:
                if not self.scroll_up():
                    return False

            i += 1

        logging.info('Итерация поиска сообщений с web-ссылками завершена.')
        return True
