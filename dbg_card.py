from animevault.models.literature import Literature, MEDIA_MANGA
from animevault.ui.card_factory import literature_card
item = Literature.create(title="Berserk", category=MEDIA_MANGA)
card = literature_card(item)
from PySide6.QtWidgets import QLabel
texts = [l.text() for l in card.findChildren(QLabel)]
print("ALL_LABELS:", texts)
