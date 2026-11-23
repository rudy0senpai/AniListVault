from PySide6.QtWidgets import QApplication
from animevault.models.literature import Literature, MEDIA_MANGA
from animevault.ui.card_factory import literature_card

app = QApplication.instance() or QApplication([])
item = Literature.create(title="Berserk", category=MEDIA_MANGA)
card = literature_card(item)
print("CARD_DONE")
