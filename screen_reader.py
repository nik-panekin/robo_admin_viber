import re
import logging

from PIL import ImageChops
from PIL.Image import Image
import numpy as np
from numpy import ndarray
import cv2
import pytesseract
from pytesseract import Output
from tld import get_tld

DOMAIN_RE = re.compile(
    r'\b(((?!-))(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]{0,1}\.'
    r'(xn--)?([a-z0-9\-]{1,61}|[a-z0-9-]{1,30}\.[a-z]{2,}))\b', re.IGNORECASE
)

URL_RE = re.compile(
    r'\b(http[s]?://(?:[a-z]|[0-9]|[$-_@.&+]|[!*\(\),]'
    r'|(?:%[0-9a-f][0-9a-f]))+)', re.IGNORECASE
)

URL_LAST_HOPE_RE = re.compile(
    r'\bhttp|\bwww|html?\b|aspx?\b|cgi\b|php\b', re.IGNORECASE
)

THRESHOLD = 190
TEMPLATE_THRESHOLD = 0.95

# DEFAULT_CONFIG = '--oem 3 --psm 6'
DEFAULT_CONFIG = ''

class ScreenReader():
    def __init__(self):
        self.image = None
        self.langs = ['eng']

    def identical_images(self, image1: Image, image2: Image) -> bool:
        try:
            if ImageChops.difference(image1, image2).getbbox() is None:
                return True
            else:
                return False
        except ValueError:
            return False

    def pillow2numpy(self, image: Image) -> ndarray:
        return np.array(image.convert('RGB'))[:, :, ::-1].copy()

    def find_template(self, image, template) -> dict:
        """Returns dict:
        {
            'conf': float,
            'left': int,
            'top': int,
            'right': int,
            'bottom': int,
        }

        If no template found returns None.
        """
        if isinstance(image, Image):
            image = self.pillow2numpy(image)
        if isinstance(template, Image):
            template = self.pillow2numpy(template)

        h, w = template.shape[:2]

        res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val < TEMPLATE_THRESHOLD:
            return None

        return {
            'conf': max_val,
            'left': max_loc[0],
            'top': max_loc[1],
            'right': max_loc[0] + w,
            'bottom': max_loc[1] + h,
        }

    def set_langs(self, langs: list):
        self.langs = langs

    def _prepare_image(self, image: ndarray) -> ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.threshold(gray, THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]

    def set_image(self, image) -> ndarray:
        if isinstance(image, Image):
            image = self.pillow2numpy(image)
        self.image = self._prepare_image(image)

    def _get_config(self):
        config = DEFAULT_CONFIG
        if self.langs:
            config = '-l ' + '+'.join(self.langs) + ' ' + config

        return config

    def get_string(self) -> str:
        if self.image is None:
            return None

        try:
            text = pytesseract.image_to_string(
                self.image, config=self._get_config()).strip()
        except Exception:
            logging.exception('Ошибка Tesseract OCR: '
                              'не удалось преобразовать изображение в текст.')
            return None

        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r'^\s+|\s+$', '', text)

        return text

    def get_words(self) -> list:
        """Returns list of dicts:
        {
            'text': str,
            'conf': float,
            'left': int,
            'top': int,
            'right': int,
            'bottom': int,
        }
        """
        if self.image is None:
            return None

        try:
            data = pytesseract.image_to_data(
                self.image, output_type=Output.DICT, config=self._get_config())
        except Exception:
            logging.exception('Ошибка Tesseract OCR: не удалось '
                              'получить подробные данные распознавания.')
            return None

        words = []
        for i in range(len(data['text'])):
            conf = float(data['conf'][i])
            text = data['text'][i].strip()
            if conf >= 0.0 and text:
                words.append({
                        'text': text,
                        'conf': conf,
                        'left': data['left'][i],
                        'top': data['top'][i],
                        'right': data['left'][i] + data['width'][i],
                        'bottom': data['top'][i] + data['height'][i],
                    })

        return sorted(words, key = lambda word: len(word['text']),
                      reverse=True)

    def find_url(self) -> str:
        text = self.get_string()
        if not text:
            return None

        # logging.info(text)
        # cv2.imwrite('screen.png', self.image)

        matches = re.findall(URL_RE, text)
        if len(matches) > 0:
            return matches[0]

        for match in re.findall(DOMAIN_RE, text):
            if not get_tld(match[0], fix_protocol=True, fail_silently=True):
                continue
            return match[0]

        matches = re.findall(URL_LAST_HOPE_RE, text)
        if len(matches) > 0:
            return matches[0]

        return None

    def locate_url(self) -> dict:
        """Returns dict:
        {
            'url': str,
            'left': int,
            'top': int,
            'right': int,
            'bottom': int,
        }

        If no URL found returns None.
        """
        url = self.find_url()
        if not url:
            return None

        for word in self.get_words():
            if (word['text'] in url) or (url in word['text']):
                return {
                    'url': url,
                    'left': word['left'],
                    'top': word['top'],
                    'right': word['right'],
                    'bottom': word['bottom'],
                }

        return None
