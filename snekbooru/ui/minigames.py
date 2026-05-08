import random
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRectF, QPropertyAnimation, pyqtProperty, QPointF, QParallelAnimationGroup
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QLineEdit, QGridLayout, QMessageBox, QGroupBox, QSpinBox,
                             QGraphicsView, QGraphicsScene, QGraphicsObject,
                             QGraphicsItem, QStyleOptionGraphicsItem)

from snekbooru.api.booru import danbooru_random, danbooru_post_count
from snekbooru.common.constants import BORING_TAGS
from snekbooru.common.translations import _tr
from snekbooru.core.workers import ApiWorker, ImageWorker


class BaseMinigame(QWidget):
    """Base class for all minigames."""
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.threadpool = self.parent_app.threadpool
        self.highscores = self.parent_app.highscores

    def get_highscore(self, game_name):
        return self.highscores.get(game_name, 0)

    def save_highscore(self, game_name, score):
        if score > self.get_highscore(game_name):
            self.highscores[game_name] = score
            return True
        return False


class PostShowdownGame(BaseMinigame):
    """A game to guess which of two posts has a higher score."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.game_name = "post_showdown"
        self.score = 0
        self.post_left = None
        self.post_right = None

        layout = QVBoxLayout(self)
        self.score_label = QLabel(_tr("Score: 0 | Highscore: {hs}").format(hs=self.get_highscore(self.game_name)))
        self.score_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.score_label)

        # Container to constrain width and center the game
        game_container = QWidget()
        game_container.setMaximumWidth(600)
        container_layout = QHBoxLayout(game_container)
        container_layout.setContentsMargins(0,0,0,0)

        game_area = QHBoxLayout()
        self.left_widget = self._create_post_widget()
        self.right_widget = self._create_post_widget()
        game_area.addWidget(self.left_widget["group"])
        game_area.addWidget(self.right_widget["group"])
        self.left_widget["button"].clicked.connect(lambda: self.make_guess('left'))
        self.right_widget["button"].clicked.connect(lambda: self.make_guess('right'))
        container_layout.addLayout(game_area)

        layout.addWidget(game_container, 0, Qt.AlignCenter)

        self.result_label = QLabel()
        self.result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.result_label)

        self.start_button = QPushButton(_tr("Start New Round"))
        self.start_button.clicked.connect(self.start_round)
        layout.addWidget(self.start_button)

        self.start_round()

    def _create_post_widget(self):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        image_label = QLabel(_tr("Loading..."))
        image_label.setFixedSize(256, 256)
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet("border: 1px solid #555;")
        button = QPushButton(_tr("Higher Score"))
        layout.addWidget(image_label)
        layout.addWidget(button)
        return {"group": group, "image": image_label, "button": button}

    def start_round(self):
        self.result_label.setText("")
        self.start_button.setText(_tr("Loading..."))
        self.start_button.setEnabled(False)
        self.left_widget["button"].setEnabled(False)
        self.right_widget["button"].setEnabled(False)
        self.left_widget["image"].setText(_tr("Loading..."))
        self.right_widget["image"].setText(_tr("Loading..."))

        worker1 = ApiWorker(danbooru_random, "")
        worker1.signals.finished.connect(self.on_post1_loaded)
        self.threadpool.start(worker1)

        worker2 = ApiWorker(danbooru_random, "")
        worker2.signals.finished.connect(self.on_post2_loaded)
        self.threadpool.start(worker2)

    def on_post1_loaded(self, post, err):
        if err or not post:
            self.result_label.setText(_tr("Error loading post. Try again."))
            self.start_button.setEnabled(True)
            return
        self.post_left = post
        self.left_widget["group"].setTitle(_tr("Post A"))
        self._load_image(self.post_left, self.left_widget["image"])
        self.check_posts_loaded()

    def on_post2_loaded(self, post, err):
        if err or not post:
            self.result_label.setText(_tr("Error loading post. Try again."))
            self.start_button.setEnabled(True)
            return
        self.post_right = post
        self.right_widget["group"].setTitle(_tr("Post B"))
        self._load_image(self.post_right, self.right_widget["image"])
        self.check_posts_loaded()

    def _load_image(self, post, label):
        worker = ImageWorker(post["preview_url"], post)
        worker.signals.finished.connect(lambda pixmap, p: self.on_image_loaded(pixmap, label))
        self.threadpool.start(worker)

    def on_image_loaded(self, pixmap, label):
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def check_posts_loaded(self):
        if self.post_left and self.post_right:
            self.start_button.setText(_tr("Start New Round"))
            self.start_button.setEnabled(True)
            self.left_widget["button"].setEnabled(True)
            self.right_widget["button"].setEnabled(True)

    def make_guess(self, choice):
        self.left_widget["button"].setEnabled(False)
        self.right_widget["button"].setEnabled(False)

        score_left = self.post_left.get('score', 0)
        score_right = self.post_right.get('score', 0)

        correct_choice = 'left' if score_left >= score_right else 'right'

        if choice == correct_choice:
            self.score += 1
            self.result_label.setText(f"<b style='color:green;'>{_tr('Correct!')}</b> "
                                      f"({_tr('Score A')}: {score_left}, {_tr('Score B')}: {score_right})")
        else:
            self.result_label.setText(f"<b style='color:red;'>{_tr('Wrong!')}</b> "
                                      f"({_tr('Score A')}: {score_left}, {_tr('Score B')}: {score_right})")
            if self.save_highscore(self.game_name, self.score):
                QMessageBox.information(self, _tr("New Highscore!"), _tr("You set a new highscore of {score}!").format(score=self.score))
            self.score = 0

        self.update_score_label()
        QTimer.singleShot(2000, self.start_round)

    def update_score_label(self):
        self.score_label.setText(_tr("Score: {score} | Highscore: {hs}").format(score=self.score, hs=self.get_highscore(self.game_name)))


class PuzzlePieceItem(QGraphicsObject):
    """A puzzle piece that is swapped via click selection."""
    dropped = pyqtSignal()
    
    # Class variable to track selected piece
    selected_piece = None

    def __init__(self, pixmap, grid_size, piece_size, pieces_list=None, on_swap_callback=None):
        super().__init__()
        self._pixmap = pixmap
        self.grid_size = grid_size
        self.piece_size = piece_size
        self.pieces_list = pieces_list
        self.on_swap_callback = on_swap_callback
        self.is_selected = False
        self.animation = None  # Keep reference to prevent GC
        self.setAcceptHoverEvents(True)

    # This is required for QPropertyAnimation to work on a QGraphicsObject's position
    @pyqtProperty(QPointF)
    def pos(self):
        return super().pos()

    @pos.setter
    def pos(self, value):
        super().setPos(value)

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return QRectF(self._pixmap.rect())

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
        """Paints the pixmap with selection highlight."""
        painter.drawPixmap(0, 0, self._pixmap)
        
        # Draw selection border
        if self.is_selected:
            painter.setPen(QPen(QColor(255, 255, 0), 3))
            painter.drawRect(0, 0, self.piece_size, self.piece_size)

    def mousePressEvent(self, event):
        """Click to select/swap."""
        if PuzzlePieceItem.selected_piece is None:
            # First click: select this piece
            self.is_selected = True
            PuzzlePieceItem.selected_piece = self
            self.update()
        elif PuzzlePieceItem.selected_piece is self:
            # Click same piece again: deselect
            self.is_selected = False
            PuzzlePieceItem.selected_piece = None
            self.update()
        else:
            # Second click: swap with selected piece
            other = PuzzlePieceItem.selected_piece
            
            # Deselect the first piece
            other.is_selected = False
            other.update()
            
            # Perform the swap animation
            self._animate_swap(other)
            
            PuzzlePieceItem.selected_piece = None
        
        super().mousePressEvent(event)

    def _animate_swap(self, other_piece):
        """Animate both pieces to their swapped positions."""
        # Get current positions
        pos1 = self.pos
        pos2 = other_piece.pos
        
        # Create animation group to keep both animations alive
        group = QParallelAnimationGroup()
        
        # Animate this piece to other's position
        anim1 = QPropertyAnimation(self, b"pos")
        anim1.setDuration(300)
        anim1.setEndValue(pos2)
        group.addAnimation(anim1)
        
        # Animate other piece to this position
        anim2 = QPropertyAnimation(other_piece, b"pos")
        anim2.setDuration(300)
        anim2.setEndValue(pos1)
        group.addAnimation(anim2)
        
        # Store reference and start
        self.animation = group
        other_piece.animation = group
        group.start()
        
        # Emit signal when done
        self.dropped.emit()
        
        if self.on_swap_callback:
            self.on_swap_callback()


class ImageScrambleGame(BaseMinigame):
    """A game to reassemble a scrambled image."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.post = None
        self.pieces = []
        self.grid_size = 4  # 4x4 grid
        self.piece_size = 128

        layout = QVBoxLayout(self)

        # Controls
        controls_layout = QHBoxLayout()
        self.start_button = QPushButton(_tr("Load New Image"))
        self.start_button.clicked.connect(self.start_game)
        self.grid_spinbox = QSpinBox()
        self.grid_spinbox.setRange(2, 8)
        self.grid_spinbox.setValue(self.grid_size)
        self.grid_spinbox.setSuffix(_tr("x{val} Grid").format(val=self.grid_spinbox.value()))
        self.grid_spinbox.valueChanged.connect(lambda val: self.grid_spinbox.setSuffix(f"x{val} Grid"))

        self.status_label = QLabel(_tr("Click 'Load New Image' to start."))
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(QLabel(_tr("Grid Size:")))
        controls_layout.addWidget(self.grid_spinbox)
        controls_layout.addStretch()
        controls_layout.addWidget(self.status_label)
        layout.addLayout(controls_layout)

        # Game Area
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        layout.addWidget(self.view)

    def start_game(self):
        self.status_label.setText(_tr("Loading random image..."))
        self.start_button.setEnabled(False)
        self.grid_size = self.grid_spinbox.value()

        worker = ApiWorker(danbooru_random, "rating:safe")
        worker.signals.finished.connect(self.on_post_loaded)
        self.threadpool.start(worker)

    def on_post_loaded(self, post, err):
        if err or not post:
            self.status_label.setText(_tr("Error loading image. Please try again."))
            self.start_button.setEnabled(True)
            return

        self.post = post
        worker = ImageWorker(post["file_url"], post)
        worker.signals.finished.connect(self.on_image_loaded)
        self.threadpool.start(worker)

    def on_image_loaded(self, pixmap, post):
        if pixmap.isNull():
            self.status_label.setText(_tr("Failed to load image data. Trying another..."))
            self.start_game()
            return

        self.setup_puzzle(pixmap)
        self.start_button.setEnabled(True)
        self.status_label.setText(_tr("Puzzle loaded! Drag the pieces to solve it."))

    def setup_puzzle(self, pixmap):
        # Explicitly delete old pieces to ensure no layering issues
        for piece in self.pieces:
            if piece.scene() is self.scene:
                self.scene.removeItem(piece)
            piece.deleteLater()
        self.pieces.clear()
        
        self.scene.clear()

        total_size = self.piece_size * self.grid_size
        scaled_pixmap = pixmap.scaled(total_size, total_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        # Crop to square
        crop_x = (scaled_pixmap.width() - total_size) / 2
        crop_y = (scaled_pixmap.height() - total_size) / 2
        cropped_pixmap = scaled_pixmap.copy(int(crop_x), int(crop_y), total_size, total_size)

        # Draw grid lines on the background
        self.scene.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        pen = QPen(QColor(80, 80, 80))
        for i in range(self.grid_size + 1):
            self.scene.addLine(i * self.piece_size, 0, i * self.piece_size, total_size, pen)
            self.scene.addLine(0, i * self.piece_size, total_size, i * self.piece_size, pen)

        # Create and add pieces
        piece_positions = []
        for y in range(self.grid_size):
            for x in range(self.grid_size):
                piece_pixmap = cropped_pixmap.copy(x * self.piece_size, y * self.piece_size, self.piece_size, self.piece_size)
                item = PuzzlePieceItem(piece_pixmap, self.grid_size, self.piece_size, self.pieces, self.check_solution)
                item.setData(0, (x, y))  # Store original position
                item.dropped.connect(self.check_solution)
                self.pieces.append(item)
                piece_positions.append(QPoint(x * self.piece_size, y * self.piece_size))

        # Shuffle and place pieces
        random.shuffle(piece_positions)
        for i, item in enumerate(self.pieces):
            item.setPos(piece_positions[i])
            self.scene.addItem(item)

        self.scene.setSceneRect(0, 0, total_size, total_size)

    def check_solution(self):
        # This check might be called multiple times due to animations, so we add a small delay
        QTimer.singleShot(200, self._do_check_solution)

    def _do_check_solution(self):
        if not self.pieces: return # Avoid checking if puzzle is not set up
        correct_pieces = 0
        for item in self.pieces:
            original_x, original_y = item.data(0)
            # Use int() to avoid floating point inaccuracies
            current_x = int(round(item.pos.x() / self.piece_size))
            current_y = int(round(item.pos.y() / self.piece_size))

            if original_x == current_x and original_y == current_y:
                correct_pieces += 1

        if correct_pieces == len(self.pieces):
            self.on_puzzle_solved()
        else:
            self.status_label.setText(_tr("{correct}/{total} pieces in correct position.").format(
                correct=correct_pieces, total=len(self.pieces)
            ))

    def on_puzzle_solved(self):
        self.status_label.setText(_tr("Congratulations! You solved the puzzle!"))
        QMessageBox.information(self, _tr("Puzzle Solved!"), _tr("You successfully reassembled the image!"))
        # Disable dragging for all items
        for item in self.pieces:
            item.setFlag(QGraphicsItem.ItemIsMovable, False)


class TagGuesserGame(BaseMinigame):
    """A game to guess the fake tag for an image."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.game_name = "tag_guesser"
        self.score = 0
        self.post = None
        self.fake_tag = ""
        self.tag_buttons = []

        layout = QVBoxLayout(self)
        self.score_label = QLabel(_tr("Score: 0 | Highscore: {hs}").format(hs=self.get_highscore(self.game_name)))
        self.score_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.score_label)

        self.image_label = QLabel(_tr("Loading..."))
        self.image_label.setFixedSize(512, 512)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #555;")
        layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        self.tags_grid = QGridLayout()
        layout.addLayout(self.tags_grid)

        self.result_label = QLabel()
        self.result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.result_label)

        self.start_round()

    def start_round(self):
        self.result_label.setText(_tr("Find the FAKE tag!"))
        self.image_label.setText(_tr("Loading..."))
        self._clear_tag_buttons()

        # Fetch a post with a good number of tags
        worker = ApiWorker(danbooru_random, "rating:safe")
        worker.signals.finished.connect(self.on_post_loaded)
        self.threadpool.start(worker)

    def _clear_tag_buttons(self):
        for button in self.tag_buttons:
            button.deleteLater()
        self.tag_buttons.clear()

    def on_post_loaded(self, post, err):
        if err or not post:
            self.result_label.setText(_tr("Error loading post. Trying again..."))
            self.start_round()
            return

        self.post = post
        self._load_image(post)

        # Get real tags and check if there are enough
        real_tags = [t for t in post.get('tags', '').split() if t not in BORING_TAGS and ":" not in t]
        if len(real_tags) < 5:
            self.result_label.setText(_tr("Post had too few tags, trying another..."))
            QTimer.singleShot(500, self.start_round) # Try again after a short delay
            return

        # Select 5 real tags and generate a fake one
        selected_real_tags = random.sample(real_tags, 5)
        self.fake_tag = self._generate_fake_tag(real_tags)

        # Combine and shuffle
        all_choices = selected_real_tags + [self.fake_tag]
        random.shuffle(all_choices)

        # Create buttons
        for i, tag in enumerate(all_choices):
            row, col = divmod(i, 3)
            button = QPushButton(tag.replace('_', ' '))
            button.clicked.connect(lambda _, t=tag: self.make_guess(t))
            self.tags_grid.addWidget(button, row, col)
            self.tag_buttons.append(button)

    def _load_image(self, post):
        worker = ImageWorker(post.get("preview_url"), post)
        worker.signals.finished.connect(self.on_tag_guesser_image_loaded)
        self.threadpool.start(worker)

    def on_tag_guesser_image_loaded(self, pixmap, post):
        if post.get('id') != self.post.get('id'): return # Stale image
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _generate_fake_tag(self, existing_tags):
        """Generates a plausible but non-existent tag."""
        # Strategy 1: Combine parts of two different tags.
        attempts = 0
        while attempts < 10:
            attempts += 1
            try:
                tag1, tag2 = random.sample(existing_tags, 2)
                parts1 = tag1.split('_')
                parts2 = tag2.split('_')

                if len(parts1) > 0 and len(parts2) > 0:
                    # Combine first part of tag1 with last part of tag2
                    fake_tag = f"{parts1[0]}_{parts2[-1]}"
                    # Ensure the generated tag is actually fake and not a simple duplicate
                    if fake_tag not in existing_tags and fake_tag != tag1 and fake_tag != tag2:
                        return fake_tag
            except (ValueError, IndexError):
                continue # Not enough tags or tags are not splittable

        # Strategy 2 (Fallback): Swap letters in a single tag.
        # This ensures a fake tag is always generated even if combination fails.
        for _ in range(10): # Try a few times to find a suitable tag
            base_tag = random.choice(existing_tags)
            if len(base_tag) > 4:
                pos1, pos2 = random.sample(range(len(base_tag)), 2)
                tag_list = list(base_tag)
                tag_list[pos1], tag_list[pos2] = tag_list[pos2], tag_list[pos1]
                swapped_tag = "".join(tag_list)
                if swapped_tag not in existing_tags:
                    return swapped_tag
        
        return random.choice(existing_tags) + "_x" # Final fallback

    def make_guess(self, guessed_tag):
        for button in self.tag_buttons:
            button.setEnabled(False)

        if guessed_tag == self.fake_tag:
            self.score += 1
            self.result_label.setText(f"<b style='color:green;'>{_tr('Correct!')}</b> '{guessed_tag.replace('_', ' ')}' was the fake tag!")
        else:
            self.result_label.setText(f"<b style='color:red;'>{_tr('Wrong!')}</b> The fake tag was '{self.fake_tag.replace('_', ' ')}'.")
            if self.save_highscore(self.game_name, self.score):
                QMessageBox.information(self, _tr("New Highscore!"), _tr("You set a new highscore of {score}!").format(score=self.score))
            self.score = 0

        self.update_score_label()
        QTimer.singleShot(2500, self.start_round)

    def update_score_label(self):
        self.score_label.setText(_tr("Score: {score} | Highscore: {hs}").format(score=self.score, hs=self.get_highscore(self.game_name)))