#! /usr/bin/env python3
import logging
import sys

import yaml
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QDialog, QLabel, QGridLayout, QPushButton
from PyQt5.QtGui import QFont

import photo_utils
from media_players import VideoPlayer, PhotoPlayer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

CONFIG_FILE = "config.yml"


class Popup(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlag(Qt.FramelessWindowHint)

        self.labels = ["Filename:", "Date:", "Location:"]   # static labels
        # list of QLabel widgets, each corresponding to a static label
        self.value_widgets = None
        self._build_UI()

    def show_image_details(self, filename, exif_tags):
        logger.debug("exif tags: %s", exif_tags)

        logger.info("Filename: %s", filename)
        self.value_widgets[0].setText(filename)

        # extract EXIF data (if any)
        date = location = "<unknown>"
        long_ref = long = lat_ref = lat = ""
        if "EXIF DateTimeOriginal" in exif_tags.keys():
            date = str(exif_tags["EXIF DateTimeOriginal"])

        if "GPS GPSLatitudeRef" in exif_tags.keys():
            lat_ref = exif_tags["GPS GPSLatitudeRef"]

        if "GPS GPSLatitude" in exif_tags.keys():
            lat = exif_tags["GPS GPSLatitude"]

        if "GPS GPSLongitudeRef" in exif_tags.keys():
            long_ref = exif_tags["GPS GPSLongitudeRef"]

        if "GPS GPSLongitude" in exif_tags.keys():
            long = exif_tags["GPS GPSLongitude"]

        # if we have GPS data, reverse lookup address
        if all([lat, lat_ref, long, long_ref]):
            lat_d, lat_m, lat_s = tuple(lat.values)
            long_d, long_m, long_s = tuple(long.values)
            location = photo_utils.get_location(lat_d.num / lat_d.den, lat_m.num / lat_m.den, lat_s.num / lat_s.den, lat_ref, long_d.num / long_d.den, long_m.num / long_m.den, long_s.num / long_s.den, long_ref)

            # reformat lines
            location = "\n".join(location.split(", "))

        self.value_widgets[1].setText(date)
        self.value_widgets[2].setText(location)
        # self.date_label.adjustSize()
        self.show()

    def _build_UI(self):
        layout = QGridLayout(self)
        self.value_widgets = []

        # font used in popup dialog
        font = QFont()
        font.setPointSize(14)

        # create labels and empty values
        for y, label in enumerate(self.labels):
            label_widget = QLabel(label, self)
            label_widget.setAlignment(QtCore.Qt.AlignRight)
            label_widget.setFont(font)
            layout.addWidget(label_widget, y, 0)

            value_widget = QLabel(self)
            value_widget.setFont(font)
            layout.addWidget(value_widget, y, 1)
            self.value_widgets.append(value_widget)

        whatsapp_button = QPushButton("Send photo", self)
        whatsapp_button.clicked.connect(self.on_click)
        layout.addWidget(whatsapp_button)

    @pyqtSlot()
    def on_click(self):
        logger.info("PyQt5 button click. TODO")


class PhotoFrame(QtWidgets.QMainWindow):
    def __init__(self, config):
        super(PhotoFrame, self).__init__()

        self.players = None
        self.current_player_index = 0

        self.config = config
        self.setup_general_config()
        self.setup_players()

        self._build_UI()
        self.popup = None
        self.showFullScreen()

        # start timer
        timer = QtCore.QTimer(self)
        timer.timeout.connect(self._timer_callback)
        timer.start(self.slideshow_delay)

        # go...
        self.get_current_player().show_current_media()

    def setup_general_config(self):
        frame_config = self._get_config_value(self.config, "frame", None)
        if not frame_config:
            raise KeyError("Could not find section 'frame' in config file. Exiting")

        self.slideshow_delay = self._get_config_value(frame_config, "slideshow_delay", 5000)
        logger.info("Slideshow delay = %s", self.slideshow_delay)
        self.media_folder = self._get_config_value(frame_config, "media_folder", "tmp")
        logger.info("Media folder = %s", self.media_folder)

    def setup_players(self):
        """
        Factory method to create the set of media players

        :return: a list of AbstractMediaPlayer instances
        """
        players_config = self._get_config_value(self.config, "players", None)
        if not players_config:
            raise KeyError("Could not find section 'players' in config file. Exiting")

        self.players = []

        # iterate through each entry, creating a corresponding media player
        for item in players_config:
            if players_config[item]["type"] == "photo_player":
                player = PhotoPlayer(item, self.media_folder + "/" + players_config[item]["folder"])
            if players_config[item]["type"] == "video_player":
                player = VideoPlayer(item, self.media_folder + "/" + players_config[item]["folder"])
                logger.info("Creating player %s", player.get_name())
            self.players.append(player)
        self.current_player_index = 0

    @staticmethod
    def _get_config_value(config, key, default):
        if not (config and key):
            logger.debug("Using default for config value %s = %s", key, default)
            return default

        try:
            value = config[key]
        except KeyError:
            logger.debug("Using default for config value %s = %s", key, default)
            return default
        logger.debug("Config value %s = %s", key, value)
        return value

    def next_player(self):
        """
        Switch to the next media player. If at the end of the player list, jump to the start
        """
        logger.debug("current_player_index = %d", self.current_player_index)
        logger.debug("length player_list = %d", len(self.players))
        if self.current_player_index >= len(self.players) - 1:
            logger.debug("Starting at beginning of media")
            new_index = 0
        else:
            new_index = self.current_player_index + 1

        self._set_player_by_index(new_index)

    def prev_player(self):
        """
        Switch to the previous media player. If at the end of the player list, jump to the start
        """
        logger.debug("current_player_index = %d", self.current_player_index)
        logger.debug("length player_list = %d", len(self.players))
        if self.current_player_index <= 0:
            logger.debug("Starting at end of players")
            new_index = len(self.players) - 1
        else:
            new_index = self.current_player_index - 1

        self._set_player_by_index(new_index)

    def get_current_player(self):
        """
        Get a reference to the current media player

        :return: the current media player
        """
        return self.players[self.current_player_index]

    def _timer_callback(self):
        self.get_current_player().next()

    def _build_UI(self):
        # setup UI - use a QStackedWidget to avoid widgets being destroyed
        self.stack = QtWidgets.QStackedWidget(self)
        for p in self.players:
            player_widget = p.get_main_widget()

            # If the media player returns a widget, add it. Else create a dummy 'not implemented' widget
            if player_widget:
                player_widget.setParent(self)
                self.stack.addWidget(player_widget)
            else:
                not_implemented = QtWidgets.QLabel("Media Player %s: Not yet implemented" % p.get_name(), self)
                not_implemented.setAlignment(QtCore.Qt.AlignCenter)
                self.stack.addWidget(not_implemented)
        self.setCentralWidget(self.stack)

    def _set_player_by_index(self, index):
        new_player = self.players[index]
        logger.debug("Changing to player index %d (%s)", index, new_player.get_name())
        self.stack.setCurrentIndex(index)
        self.current_player_index = index
        new_player.show_current_media()

    def mousePressEvent(self, mouse):
        """
        Handle mouse clicks

        :param mouse: the mouse event
        """

        # close the popup (if open)
        popup_closed = False
        if self.popup and self.popup.isVisible():
            self.popup.hide()
            popup_closed = True

        # get the width/height of the screen, and the mouse click lco-ords
        width, height = self.size().width(), self.size().height()
        x, y = mouse.pos().x(), mouse.pos().y()


        # click on left/right borders = prev/next image
        if x >= width * 0.8:
            self.get_current_player().next()
        elif x <= width * 0.2:
            self.get_current_player().prev()

        # click on the top/bottom borders = prev/next media player
        elif y >= height * 0.8:
            self.next_player()
        elif y <= height * 0.2:
            self.prev_player()

        # click in the centre = raise popup showing photo information
        elif not popup_closed:
            logger.info("Open popup")
            if not self.popup:
                self.popup = Popup()
            filename, exif = self.get_current_player().get_current_media_exif()
            self.popup.show_image_details(filename, exif)

    def keyPressEvent(self, key):
        """
        Handle key-presses

        :param key: the pressed key
        """
        key_press = key.key()
        if key_press == QtCore.Qt.Key_Escape:   # escape = exit
            self.close()
            sys.exit(0)

        if key_press == QtCore.Qt.Key_Left:     # left = prev image
            self.get_current_player().prev()

        if key_press == QtCore.Qt.Key_Right:    # right = next image
            self.get_current_player().next()

        if key_press == QtCore.Qt.Key_Up:       # up = next media player
            self.prev_player()

        if key_press == 32:                     # space = reload image list
            self.refresh_current_playlist()

        if key_press == QtCore.Qt.Key_Down:     # down = next player
            self.next_player()

    def refresh_current_playlist(self):
        self.get_current_player().refresh_media_list()


def exception_hook(exctype, value, traceback):
    """
    Handle exceptions in the Qt application. Prevents exceptions being consumed silently by Qt.
    :param exctype: the type of exception
    :param value: the exception contents
    :param traceback: the stack trace
    """
    # Print the error and traceback
    print(exctype, value, traceback)
    # Call the normal Exception hook after
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


def read_config():
    """
    Read configuration file and return a dictionary of parameters

    :return: a dictionary of parameters representing the YAML file (see YAML spec)
    """
    try:
        with open(CONFIG_FILE, 'r') as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
    except FileNotFoundError:
        logger.error("Could not load config file %s. Exiting.", CONFIG_FILE)
        sys.exit(1)
    # data = yaml.dump(cfg, Dumper=yaml.CDumper)
    # print(data)
    return cfg


def main():
    """
    Create the photo frame application
    """
    sys._excepthook = sys.excepthook
    sys.excepthook = exception_hook

    app = QtWidgets.QApplication(sys.argv)

    try:
        window = PhotoFrame(read_config())
        window.raise_()
    except KeyError as e:
        print(e)
        sys.exit(1)

    app.exec_()


if __name__ == '__main__':
    main()
