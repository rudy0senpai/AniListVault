from animevault.models.literature import Literature, MEDIA_MANGA
from animevault.ui.card_factory import literature_card
from animevault.media_types import unit_for
item = Literature.create(title="Berserk", category=MEDIA_MANGA, chapters=200, chapters_read=50)
card = literature_card(item)
from PySide6.QtWidgets import QLabel
texts = [l.text() for l in card.findChildren(QLabel)]
print("ALL_LABELS:", texts)
print("unit_for(MEDIA_MANGA):", unit_for(MEDIA_MANGA))
